import unittest

from tools.text_to_speech import spoken_form


class SpokenFormTests(unittest.TestCase):
    def test_numbers_units_and_times(self):
        for text, spoken in [
            ('drew about 243.0 mA, averaging 1781.0 mW.', 'drew about 243 milliamps, averaging 1781 milliwatts.'),
            ('dropped to 7.33 V', 'dropped to 7 point three three volts'),
            ('around -824.0 mA.', 'around minus 824 milliamps.'),
            ('at 0:05, and again at 1:11', 'at 5 seconds, and again at 1 minute 11 seconds'),
            ('one at 14638.8 Hz with 7.2 dB', 'one at 14638 point eight hertz with 7 point two decibels'),
            ('a peak of 0.03 g near 2 kHz', 'a peak of zero point zero three g near 2 kilohertz'),
            ('levels in dB below full scale', 'levels in decibels below full scale'),
            ('1 V, 1.0 mAh, 12.1 mWh, 50.0%', '1 volt, 1 milliamp hour, 12 point one milliwatt hours, 50 percent'),
            ('tilted 12.5° for 3 s', 'tilted 12 point five degrees for 3 seconds'),
            ('It ran for 3 seconds. A steady tone.', 'It ran for 3 seconds. A steady tone.'),
        ]:
            self.assertEqual(spoken_form(text), spoken)


if __name__ == '__main__':
    unittest.main()
