# Copyright (c) 2018 Blizzard Entertainment
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import struct


class TruncatedError(Exception):
    pass


class CorruptedError(Exception):
    pass


class BitPackedBuffer:
    def __init__(self, contents, endian='big'):
        self._data = contents or []
        self._datalen = len(self._data)
        self._datagen = iter(self._data)
        self._used = 0
        self._next = 0
        self._nextbits = 0
        self._bigendian = (endian == 'big')

    def __str__(self):
        return 'buffer(%02x/%d)' % (self._next or 0, self._nextbits)
    def done(self):
        # return self._nextbits == 0 and self._used >= len(self._data)
        # NOTE:  this method is broken
        if self._next is None:
            return True

        if self._nextbits == 0:
            self._next = next(self._datagen, None)
            self._nextbits = 8

            return self._next is None
        else:
            return False

    def used_bits(self):
        return 0

    def byte_align(self):
        self._nextbits = 0

    def read_aligned_bytes(self, num_bytes):
        self.byte_align()
        return bytes(next(self._datagen) for i in range(0, num_bytes))

    def read_bits(self, bits):

        # Special case for when we aren't reading any bits
        if bits == 0:
            return 0

        # cache the class variables as locals to reduce pointer dereferences
        _next = self._next
        _nextbits = self._nextbits
        _bigendian = self._bigendian
        _datagen = self._datagen

        result = 0
        remaining_bits = bits # this is the number of bits remaining to be read.
        read_bits = 0 # only increment this in little-endian mode

        while True:
            if _nextbits == 0:
                _next = _datagen.__next__()
                _nextbits = 8

            if remaining_bits > _nextbits:
                copy = _next
                remaining_bits -= _nextbits

                if _bigendian:
                    result |= copy << remaining_bits
                else:
                    #print(little_endian_last_read_size - read_bits)
                    result |= copy << read_bits
                    read_bits += _nextbits
                _nextbits = 0
            else:
                copy = _next & ((1 << remaining_bits) - 1) # we are creating a mask here by 1 << 3 == 1000 - 1 = 0111
                _next = _next >> remaining_bits # we are removing the bits that we just used here.
                _nextbits -= remaining_bits

                if _bigendian:
                    result |= copy
                else:
                    result |= copy << read_bits

                break

        self._next = _next
        self._nextbits = _nextbits

        return result

    def read_unaligned_bytes(self, num_bytes):
        #read_bits is slow, so doing a trivial check to see if we are at a bytes boundary
        if self._nextbits == 0:
            return bytes(next(self._datagen) for i in range(0,num_bytes))
        else:
            return bytes(self.read_bits(8) for i in range(0,num_bytes))


class BitPackedDecoder:

    def __init__(self, contents, typeinfos):
        self._buffer = BitPackedBuffer(contents)

        self._typeinfo_functions = []
        self._typeinfo_len = len(typeinfos)

        # NOTE:  this class has been re-written to use closures.
        # All of the named functionality now return a function, which when executed actually does the dirty work.
        # instance functions the same as before.  If you want to get a reference to a given function, use _lookup
        # ASSUMPTION:  structs & related only use previously declared functions
        for funcName, args_array in typeinfos:
            funcObj = getattr(self, funcName)(*args_array)
            self._typeinfo_functions.append(funcObj)

    def __str__(self):
        return self._buffer.__str__()

    def _lookup(self, typeid):
        return self._typeinfo_functions[typeid]

    def instance(self, typeid):
        #if typeid >= self._typeinfo_len:
        #    raise CorruptedError(self)
        # typeinfo = self._typeinfos[typeid]
        return self._typeinfo_functions[typeid]()
        #return self._typeinfos_lookup[typeid](*self._typeinfos_args[typeid])

    def byte_align(self):
        self._buffer.byte_align()

    def done(self):
        return self._buffer.done()

    def used_bits(self):
        return self._buffer.used_bits()

    def _array(self, bounds, typeid):
        int_func = self._int(bounds)

        def _array_closure():
            length = int_func()
            type_lookup = self._lookup(typeid)
            return [type_lookup() for i in range(0,length)]

        return _array_closure

    def _bitarray(self, bounds):
        int_func = self._int(bounds)

        def _bitarray_closure():
            length = int_func()
            return (length, self._buffer.read_bits(length))
        return _bitarray_closure

    def _blob(self, bounds):
        int_func = self._int(bounds)

        def _blob_closure():
            length = int_func()
            result = self._buffer.read_aligned_bytes(length)
            try:
                result = result.decode('utf-8')
            except UnicodeDecodeError:
                pass
            return result
        return _blob_closure

    def _bool(self):
        def _bool_closure():
            return self._buffer.read_bits(1) != 0
        return _bool_closure

    def _choice(self, bounds, fields):
        tag_func = self._int(bounds)
        field_lookup = {}

        for index in fields:
            name, typeid = fields[index]
            field_lookup[index] = (name, self._lookup(typeid))

        def _choice_closure():
            tag = tag_func()
            if tag not in fields:
                raise CorruptedError(self)
            field_name, field_func = field_lookup[tag]
            return {field_name: field_func()}

        return _choice_closure

    def _fourcc(self):
        def _fourcc_closure():
            #  bug fix for hero mastery levels.  Bytes were decoding backwards.
            return struct.pack('>I', self._buffer.read_bits(32)).decode('utf-8')
        return _fourcc_closure

    def _int(self, bounds):
        _buffer = self._buffer
        if bounds[0] == 0:
            def _int0_closure():
                return _buffer.read_bits(bounds[1])
            return _int0_closure
        else:
            def _int_closure():
                return bounds[0] + _buffer.read_bits(bounds[1])
            return _int_closure

    def _null(self):
        def _null_closure():
            return None
        return _null_closure

    def _optional(self, typeid):
        bool_func = self._bool()
        exec_func = self._lookup(typeid)

        def _optional_closure():
            exists = bool_func()
            return exec_func() if exists else None
        return _optional_closure

    def _real32(self):
        def _real32_closure():
            return struct.unpack('>f', self._buffer.read_unaligned_bytes(4))
        return _real32_closure

    def _real64(self):
        def _real64_closure():
            return struct.unpack('>d', self._buffer.read_unaligned_bytes(8))
        return _real64_closure

    def _struct(self, fields):
        # Adding assumption that parent is the first field in the _struct, if it's there.
        parent_func = None

        fields_lookup = []

        for name, typeid, index in fields:
            field_func = self._lookup(typeid)
            if name == '__parent':
                parent_func = field_func
            else:
                fields_lookup.append( (name, field_func))

        def _struct_closure():
            result = {}
            if parent_func is not None:
                parent_result = parent_func()
                if isinstance(parent_result, dict):
                    result = parent_result
                else:
                    result['__parent'] = parent_result

            for name, exec_func in fields_lookup:
                result[name] = exec_func()
            return result

        return _struct_closure

class VersionedDecoder:
    def __init__(self, contents, typeinfos):
        self._buffer = BitPackedBuffer(contents)
        self._typeinfos = typeinfos

    def __str__(self):
        return self._buffer.__str__()

    def instance(self, typeid):
        if typeid >= len(self._typeinfos):
            raise CorruptedError(self)
        typeinfo = self._typeinfos[typeid]
        return getattr(self, typeinfo[0])(*typeinfo[1])

    def byte_align(self):
        self._buffer.byte_align()

    def done(self):
        return self._buffer.done()

    def used_bits(self):
        return self._buffer.used_bits()

    def _expect_skip(self, expected):
        if self._buffer.read_bits(8) != expected:
            raise CorruptedError(self)

    def _vint(self):
        b = self._buffer.read_bits(8)
        negative = b & 1
        result = (b >> 1) & 0x3f
        bits = 6
        while (b & 0x80) != 0:
            b = self._buffer.read_bits(8)
            result |= (b & 0x7f) << bits
            bits += 7
        return -result if negative else result

    def _array(self, bounds, typeid):
        self._expect_skip(0)
        length = self._vint()
        return [self.instance(typeid) for i in range(0,length)]

    def _bitarray(self, bounds):
        self._expect_skip(1)
        length = self._vint()
        return (length, self._buffer.read_aligned_bytes((length + 7) / 8))

    def _blob(self, bounds):
        self._expect_skip(2)
        length = self._vint()
        result = self._buffer.read_aligned_bytes(length)
        try:
            result = result.decode('utf-8')
        except UnicodeDecodeError:
            pass
        return result

    def _bool(self):
        self._expect_skip(6)
        return self._buffer.read_bits(8) != 0

    def _choice(self, bounds, fields):
        self._expect_skip(3)
        tag = self._vint()
        if tag not in fields:
            self._skip_instance()
            return {}
        field = fields[tag]
        return {field[0]: self.instance(field[1])}

    def _fourcc(self):
        self._expect_skip(7)
        return self._buffer.read_aligned_bytes(4)

    def _int(self, bounds):
        self._expect_skip(9)
        return self._vint()

    def _null(self):
        return None

    def _optional(self, typeid):
        self._expect_skip(4)
        exists = self._buffer.read_bits(8) != 0
        return self.instance(typeid) if exists else None

    def _real32(self):
        self._expect_skip(7)
        return struct.unpack('>f', self._buffer.read_aligned_bytes(4))

    def _real64(self):
        self._expect_skip(8)
        return struct.unpack('>d', self._buffer.read_aligned_bytes(8))

    def _struct(self, fields):
        self._expect_skip(5)
        result = {}
        length = self._vint()
        for i in range(0,length):
            tag = self._vint()
            field = next((f for f in fields if f[2] == tag), None)
            if field:
                if field[0] == '__parent':
                    parent = self.instance(field[1])
                    if isinstance(parent, dict):
                        result.update(parent)
                    elif len(fields) == 1:
                        result = parent
                    else:
                        result[field[0]] = parent
                else:
                    result[field[0]] = self.instance(field[1])
            else:
                self._skip_instance()
        return result

    def _skip_instance(self):
        skip = self._buffer.read_bits(8)
        if skip == 0:  # array
            length = self._vint()
            for i in range(0,length):
                self._skip_instance()
        elif skip == 1:  # bitblob
            length = self._vint()
            self._buffer.read_aligned_bytes((length + 7) / 8)
        elif skip == 2:  # blob
            length = self._vint()
            self._buffer.read_aligned_bytes(length)
        elif skip == 3:  # choice
            tag = self._vint()
            self._skip_instance()
        elif skip == 4:  # optional
            exists = self._buffer.read_bits(8) != 0
            if exists:
                self._skip_instance()
        elif skip == 5:  # struct
            length = self._vint()
            for i in range(0,length):
                tag = self._vint()
                self._skip_instance()
        elif skip == 6:  # u8
            self._buffer.read_aligned_bytes(1)
        elif skip == 7:  # u32
            self._buffer.read_aligned_bytes(4)
        elif skip == 8:  # u64
            self._buffer.read_aligned_bytes(8)
        elif skip == 9:  # vint
            self._vint()
