"""BMI270 failures must not publish zero/stale axes as successful readings."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class ImuCheckedTests(unittest.TestCase):
    def test_initialization_configuration_and_read_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'bmi270.h').write_text('''#pragma once
#include <cstdint>
constexpr int8_t BMI2_OK=0,BMI2_E_NULL_PTR=-1,BMI2_E_INVALID_STATUS=-21;
constexpr uint8_t BMI2_ACCEL=0,BMI2_GYRO=1,BMI2_ACC_ODR_200HZ=9,BMI2_GYR_ODR_200HZ=9,BMI2_ACC_RANGE_4G=1,BMI2_GYR_RANGE_1000=1;
struct bmi2_dev {int identity;};
struct axes {int16_t x,y,z;};
struct bmi2_sens_data {axes acc,gyr;uint32_t sens_time;uint8_t status;};
struct config {uint8_t odr,range;};
struct bmi2_sens_config {uint8_t type;union {config acc,gyr;} cfg;};
extern "C" {
int8_t bmi2_get_sensor_config(bmi2_sens_config*,uint8_t,bmi2_dev*);
int8_t bmi270_set_sensor_config(bmi2_sens_config*,uint8_t,bmi2_dev*);
int8_t bmi270_sensor_enable(const uint8_t*,uint8_t,bmi2_dev*);
int8_t bmi2_get_sensor_data(bmi2_sens_data*,bmi2_dev*);
}
''')
            (root/'test.cpp').write_text(r'''
#include "imu_checked.h"
#include <cassert>
extern "C" int8_t __wrap_bmi270_init(bmi2_dev*);
int8_t init_result=0,read_result=0;int fail_call=0,call=0;bool mismatch=false;bool configured=false;
bmi2_dev device{42};
extern "C" int8_t __real_bmi270_init(bmi2_dev* p) {assert(p==&device);return init_result;}
int8_t status(bmi2_dev* p) {assert(p==&device);return ++call==fail_call ? -7:0;}
extern "C" int8_t bmi2_get_sensor_config(bmi2_sens_config* c,uint8_t n,bmi2_dev* p) {
 assert(n==2 && c[0].type==BMI2_ACCEL && c[1].type==BMI2_GYRO);
 if (configured) {c[0].cfg.acc={BMI2_ACC_ODR_200HZ,BMI2_ACC_RANGE_4G};c[1].cfg.gyr={BMI2_GYR_ODR_200HZ,BMI2_GYR_RANGE_1000};}
 if (mismatch) c[0].cfg.acc.odr=0;return status(p);
}
extern "C" int8_t bmi270_set_sensor_config(bmi2_sens_config* c,uint8_t n,bmi2_dev* p) {
 assert(n==2 && c[0].cfg.acc.odr==BMI2_ACC_ODR_200HZ && c[0].cfg.acc.range==BMI2_ACC_RANGE_4G);
 assert(c[1].cfg.gyr.odr==BMI2_GYR_ODR_200HZ && c[1].cfg.gyr.range==BMI2_GYR_RANGE_1000);
 configured=true;return status(p);
}
extern "C" int8_t bmi270_sensor_enable(const uint8_t* sensors,uint8_t n,bmi2_dev* p) {
 assert(n==2 && sensors[0]==BMI2_ACCEL && sensors[1]==BMI2_GYRO);return status(p);
}
extern "C" int8_t bmi2_get_sensor_data(bmi2_sens_data* d,bmi2_dev* p) {
 assert(p==&device);d->acc.x=123;d->sens_time=99;d->status=0xc0;return read_result;
}
int main() {
 bmi2_sens_data data{};data.acc.x=45;
 assert(imu_read_checked(data)!=0 && data.acc.x==45);
 init_result=-5;assert(__wrap_bmi270_init(&device)==-5);
 assert(imu_configure_checked()==-5 && imu_read_checked(data)!=0);
 init_result=0;assert(__wrap_bmi270_init(&device)==0);
 for (int step=1;step<=4;++step) {
  call=0;fail_call=step;assert(imu_configure_checked()==-7);assert(imu_read_checked(data)!=0);
 }
 call=0;fail_call=0;mismatch=true;assert(imu_configure_checked()==BMI2_E_INVALID_STATUS);
 mismatch=false;call=0;assert(imu_configure_checked()==0);
 read_result=-3;assert(imu_read_checked(data)==-3 && data.acc.x==45);
 read_result=0;assert(imu_read_checked(data)==0 && data.acc.x==123 && data.sens_time==99);
 init_result=-5;assert(__wrap_bmi270_init(&device)==-5);assert(imu_read_checked(data)!=0);
}
''')
            subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(root),'-I','firmware/main',
                            str(root/'test.cpp'),'firmware/main/imu_checked.cpp','-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True)
