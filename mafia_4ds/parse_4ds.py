from struct import unpack


def read_ushort(reader):
    return unpack(b'<H', reader.read(2))[0]


def read_uint(reader):
    return unpack(b'<I', reader.read(4))[0]


def read_uint64(reader):
    return unpack(b'<Q', reader.read(8))[0]


def read_float(reader):
    return unpack(b'<f', reader.read(4))[0]


def read_doublet(reader):
    return unpack("fff", reader.read(4 * 2))


def read_triplet(reader):
    return unpack("fff", reader.read(4 * 3))


def read_ubyte(reader):
    return unpack(b'B', reader.read(1))[0]


def read_string_fixed(reader,length):
    bytes = reader.read(length)

    if bytes[-1] != 0:
        raise ValueError('Not a NULL terminated string.')

    string = bytes[:-1].decode('utf-8')  # TODO: handle exception
    return string


class FourDSFile:
    pass


class Material:
    pass


def parse(filename):
    pass
