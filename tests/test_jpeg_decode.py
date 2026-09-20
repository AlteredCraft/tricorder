"""Decode actual JPEG bytes; headers or hashes alone are insufficient image evidence."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from tools.jpeg_evidence import decode_jpeg
class JpegDecodeTests(unittest.TestCase):
    def test_complete_wrong_dimensions_and_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);raw=bytes([220,30,40])*32*16
            data=subprocess.run(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size','32x16',
                                 '-i','pipe:0','-frames:v','1','-c:v','mjpeg','-f','image2pipe','pipe:1'],input=raw,capture_output=True,check=True).stdout
            path=p/'image.json'
            def write(b):
                path.with_suffix('.bin').write_bytes(b)
                path.write_text(json.dumps({'status':'complete','size_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}))
            write(data);decode_jpeg(path,{'width':32,'height':16},p/'valid.png');self.assertTrue((p/'valid.png').exists())
            with self.assertRaises(ValueError):decode_jpeg(path,{'width':16,'height':32},p/'wrong.png')
            write(data[:-2])
            with self.assertRaises(ValueError):decode_jpeg(path,{'width':32,'height':16},p/'short.png')
            write(data+data)
            with self.assertRaises(ValueError):decode_jpeg(path,{'width':32,'height':16},p/'double.png')
