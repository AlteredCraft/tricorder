"""Verify every attempt in the isolated 100 Hz latest-register IMU baseline."""
import argparse
import json
from pathlib import Path
import struct
from tools.audio_baseline_evidence import distribution
from tools.inspect_capture import load_verified
from tools.workload_evidence import assess_cpu


def compare_imu(meta,data):
    errors=[];missing=[]
    expected={'format':'imu_baseline_i32le','rows':6000,'columns':13,'period_us':10000,
              'hardware_odr_hz':200,'accel_range_g':4,'gyro_range_dps':1000,'configuration_readback':True,
              'policy':'latest-register-sample; intermediate hardware samples intentionally not retained',
              'read_errors':0,'not_ready':0,'repeated_sensor_time':0,'missed_deadlines':0}
    for key,value in expected.items():
        if key not in meta:missing.append(key)
        elif meta[key]!=value:errors.append(key+' mismatch')
    if len(data)!=6000*52:return {'status':'fail','errors':errors+['Incomplete polling attempts'],'missing':missing}
    rows=list(struct.iter_unpack('<13i',data));previous=None
    for index,row in enumerate(rows):
        sequence,scheduled,start,end,result,sensor_time,status,*axes=row
        if sequence!=index+1 or scheduled!=(index+1)*10000 or start<scheduled-1000 or end<start or end>scheduled+10000:
            errors.append('Polling sequence/deadline mismatch');break
        if result!=0 or status & 0xc0!=0xc0 or not 0<=sensor_time<=0xffffff or any(not -32768<=v<=32767 for v in axes):
            errors.append('Invalid read/status/axis evidence');break
        if previous and (start<previous[3] or end<=previous[3] or sensor_time==previous[5]):
            errors.append('Stale or unordered polling evidence');break
        previous=row
    duration=meta.get('duration_us')
    if duration is None:missing.append('duration_us')
    elif type(duration) is not int or not 59990000<=duration<=60020000 or duration<rows[-1][3]:
        errors.append('Incomplete or late 60-second poll window')
    cpu,cpu_errors,cpu_missing=assess_cpu(meta);errors.extend(cpu_errors);missing.extend(cpu_missing)
    memory=meta.get('memory_samples',[])
    keys=('free_internal','free_psram','largest_psram','stack_margin_bytes','free_task_sram','largest_task_sram')
    if len(memory)!=60:missing.append('memory sampling cadence')
    else:
        for index,sample in enumerate(memory,1):
            if sample.get('sample_index')!=index*100:errors.append('Memory sample position mismatch')
            for key in keys:
                if key not in sample:missing.append(key)
                elif type(sample[key]) is not int or sample[key]<=0:errors.append('Invalid memory '+key)
    intervals=[b[3]-a[3] for a,b in zip(rows,rows[1:])]
    rate=5999e6/(rows[-1][3]-rows[0][3]) if rows[-1][3]>rows[0][3] else 0
    result={'status':'fail' if errors else ('inconclusive' if missing else 'pass'),'errors':errors,'missing':missing,
            'poll_hz':rate,'cpu_tasks':cpu,
            'scope':'Isolated latest-register polling; intermediate 200 Hz samples are intentionally unretained. No FIFO losslessness, calibration or combined-load claim.'}
    if not errors and not missing:
        result.update(poll_interval_us=distribution(intervals),read_duration_us=distribution([r[3]-r[2] for r in rows]),
                      deadline_lateness_us=distribution([max(0,r[2]-r[1]) for r in rows]),
                      memory_min={key:min(s[key] for s in memory) for key in keys})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('metadata',type=Path)
    args=parser.parse_args();meta,data=load_verified(args.metadata);result=compare_imu(meta,data)
    with args.metadata.with_name(args.metadata.stem+'-assessment.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
