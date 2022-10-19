from struct import unpack


def read_ushort(reader):
    return unpack(b'<H', reader.read(2))[0]


def read_uint(reader):
    return unpack(b'<I', reader.read(4))[0]


def read_ulong(reader):
    return unpack(b'<Q', reader.read(8))[0]


def read_float(reader):
    return unpack(b'<f', reader.read(4))[0]


def read_doublet(reader):
    return unpack('ff', reader.read(4 * 2))


def read_triplet(reader):
    return unpack('fff', reader.read(4 * 3))


def read_quartet(reader):
    return unpack('ffff', reader.read(4 * 4))


def read_ubyte(reader):
    return unpack(b'B', reader.read(1))[0]


def read_string_fixed(reader, length):
    bytes = reader.read(length)
    string = bytes.decode('ISO-8859-2')  # extended ascii characters appear in game files
    return string


def read_string_array(reader): # '\0'-separated array of strings, terminated with EOF
    array = []
    bytes = []

    while True:
        byte = reader.read(1)
        if byte == b'':
            return array
        elif byte == b'\0':
            bstr = b''.join(bytes)
            string = bstr.decode('ISO-8859-2')
            array.append(string)
            bytes = []
        else:
            bytes.append(byte)


def read_string(reader):
    length = read_ubyte(reader)
    return read_string_fixed(reader, length)


def read_matrix(reader):  # 4x4 float matrix
    rows = [read_quartet(reader) for _ in range(4)]
    rows = [(ntlet[0], ntlet[2], ntlet[1], ntlet[3]) for ntlet in rows]  # first order columns
    rows = [rows[0], rows[2], rows[1], rows[3]]  # then rows
    return rows


def flip_axes(ntlet):
    n = len(ntlet)
    assert n == 2 or n == 3 or n == 4

    if n == 2:
        return ntlet[0], 1-ntlet[1]
    elif n == 3:
        return ntlet[0], ntlet[2], ntlet[1]
    else:
        return ntlet[0], ntlet[1], ntlet[3], ntlet[2]
