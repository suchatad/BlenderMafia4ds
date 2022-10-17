from io_helper import *


KEY_POSITION = 2
KEY_ROTATION = 4
KEY_SCALE = 8
KEY_UNKNOWN = 16


class BoneAnimation:
    def __init__(self):
        self.has_unknown = None
        self.has_scale = None
        self.has_rotation = None
        self.has_position = None
        self.scale_keys = None
        self.scale_frames = None
        self.position_keys = None
        self.position_frames = None
        self.rotation_keys = None
        self.rotation_frames = None

    def read(self, reader):
        flags = read_uint(reader)

        self.has_position = (flags & KEY_POSITION) != 0
        self.has_rotation = (flags & KEY_ROTATION) != 0
        self.has_scale = (flags & KEY_SCALE) != 0
        self.has_unknown = (flags & KEY_UNKNOWN) != 0

        if self.has_rotation:
            num_rotation_frames = read_ushort(reader)
            self.rotation_frames = [read_ushort(reader) for _ in range(num_rotation_frames)]
            self.rotation_keys = [read_quartet(reader) for _ in range(num_rotation_frames)]

        if self.has_position:
            num_position_frames = read_ushort(reader)
            self.position_frames = [read_ushort(reader) for _ in range(num_position_frames)]

            if num_position_frames % 2 == 0:
                read_ushort(reader)

            self.position_keys = [flip_axes(read_triplet(reader)) for _ in range(num_position_frames)]

        if self.has_scale:
            num_scale_frames = read_ushort(reader)
            self.scale_frames = [read_ushort(reader) for _ in range(num_scale_frames)]

            if num_scale_frames % 2 == 0:
                read_ushort(reader)

            self.scale_keys = [read_triplet(reader) for _ in range(num_scale_frames)]

        if self.has_unknown:
            num_unknown_frames = read_ushort(reader)
            read_ushort(reader)

            for _ in range(num_unknown_frames):
                read_uint(reader)

    def write(self, writer):
        raise NotImplementedError()


class FiveDSFile:
    def __init__(self):
        self.version = None
        self.timestamp = None
        self.unknown_1 = None
        self.num_frames = None
        self.bone_animations = None
        self.links = None
        self.bone_names = None

    def read(self, reader):
        magic = read_string_fixed(reader, 4)
        if magic != '5DS\0':
            raise ValueError("Not a 5ds file.")

        self.version = read_ushort(reader)
        if self.version != 20:
            raise ValueError("Not a Mafia 5ds file.")

        self.timestamp = read_ulong(reader)
        self.unknown_1 = read_uint(reader)

        num_bones = read_ushort(reader)
        self.num_frames = read_ushort(reader)

        self.links = [(read_uint(reader), read_uint(reader)) for _ in range(num_bones)]

        self.bone_animations = []
        for _ in range(num_bones):
            anim = BoneAnimation()
            anim.read(reader)
            self.bone_animations.append(anim)

        self.bone_names = read_string_array(reader)
        assert len(self.bone_names) == num_bones

    def write(self, writer):
        raise NotImplementedError()
