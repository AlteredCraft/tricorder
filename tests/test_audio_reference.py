import math
import unittest

from tools.audio_reference import spectrum


class AudioReferenceTests(unittest.TestCase):
    def test_bin_centered_tone_recovers_frequency_and_amplitude(self):
        samples = [.3*math.sin(2*math.pi*3*n/32) for n in range(32)]
        result = spectrum(samples, 48000)
        self.assertEqual(result['peak_bin'], 3)
        self.assertEqual(result['peak_hz'], 4500)
        self.assertAlmostEqual(result['peak_amplitude_fs'], .3, places=12)

    def test_dc_and_nyquist_are_not_doubled(self):
        dc = spectrum([.2]*32, 48000)['amplitude_fs']
        nyquist = spectrum([.2*(-1)**n for n in range(32)], 48000)['amplitude_fs']
        self.assertAlmostEqual(dc[0], .2, places=12)
        self.assertAlmostEqual(nyquist[-1], .2, places=12)

    def test_silence_has_no_dominant_frequency(self):
        result = spectrum([0.0]*32, 48000)
        self.assertIsNone(result['peak_bin'])
        self.assertIsNone(result['peak_hz'])
        self.assertEqual(result['amplitude_fs'], [0.0]*17)

    def test_centered_impulse_has_expected_flat_interior(self):
        samples = [0.0]*32
        samples[16] = .5
        reference = spectrum(samples, 48000)
        self.assertIsNone(reference['peak_hz'])
        result = reference['amplitude_fs']
        for value in result[1:-1]:
            self.assertAlmostEqual(value, .0625, places=12)
        self.assertAlmostEqual(result[0], .03125, places=12)

    def test_invalid_data_and_rates_are_rejected(self):
        for samples, rate in [([0.0]*3, 48000), ([0.0]*32, 0),
                              ([float('nan')]*32, 48000), ([1.1]*32, 48000)]:
            with self.subTest(rate=rate, length=len(samples)):
                with self.assertRaises(ValueError):
                    spectrum(samples, rate)
