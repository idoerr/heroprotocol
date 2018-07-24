
import unittest
import struct

from decoders import *

class TestBitDecododer(unittest.TestCase):

    def test_basic(self):
        testdata = int('00000000 11111111 00001111 11110000'.replace(' ', ''), 2)
        data = struct.pack('<I', testdata )

        decoder = BitPackedBuffer(data)

        self.assertFalse(decoder.done())

        self.assertEqual(0xF0, decoder.read_bits(8))
        self.assertEqual(0x0F, decoder.read_bits(8))

        self.assertFalse(decoder.done())

        self.assertEqual(0xFF, decoder.read_bits(8))
        self.assertEqual(0x00, decoder.read_bits(8))

        self.assertTrue(decoder.done())

    def test_basic_offset(self):
        testdata = int('00000000 00111100 00001111 11110000'.replace(' ', ''), 2)
        data = struct.pack('<I', testdata)

        decoder = BitPackedBuffer(data)

        self.assertEqual(0x00, decoder.read_bits(4))
        self.assertEqual(0xFF, decoder.read_bits(8))
        self.assertEqual(0x00, decoder.read_bits(6))
        self.assertEqual(0x0f, decoder.read_bits(4))
        self.assertEqual(0x00, decoder.read_bits(10))

    def test_long_offset(self):
        testdata = int('00111001 11110000 01111111 11111100'.replace(' ', ''), 2)
        data = struct.pack('<I', testdata)

        decoder = BitPackedBuffer(data)

        self.assertEqual(0x00, decoder.read_bits(2))
        self.assertEqual(0x1FFF, decoder.read_bits(13))
        self.assertEqual(0x00, decoder.read_bits(5))
        self.assertEqual(0x1F, decoder.read_bits(5))
        self.assertEqual(0x00, decoder.read_bits(2))
        self.assertEqual(0x07, decoder.read_bits(3))
        self.assertEqual(0x00, decoder.read_bits(2))

    def test_basic_endian(self):

        testdata = int('11111111 00000000'.replace(' ', ''), 2)
        data = struct.pack('<I', testdata)

        bigdecoder = BitPackedBuffer(data, 'big')

        self.assertEqual(0x00FF, bigdecoder.read_bits(16))

        littledecoder = BitPackedBuffer(data, 'little')
        self.assertEqual(0xFF00, littledecoder.read_bits(16))


    def test_little_endian_basic(self):
        testdata = int('11111 11000011 11110010 11100001 000'.replace(' ', ''), 2)
        data = struct.pack('<I', testdata)

        decoder = BitPackedBuffer(data, 'little')

        decoder.read_bits(3)
        self.assertEqual(0xF2E1, decoder.read_bits(16))
        self.assertEqual(0x1FC3, decoder.read_bits(13))
        self.assertEqual(0x7F, decoder.read_bits(7))
        #self.assertEqual(1, decoder.read_bits(8))


if __name__ == '__main__':
    unittest.main()