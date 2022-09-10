from struct import unpack
import numpy as np


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
    string = bytes.decode('utf-8')
    return string


def read_string(reader):
    length = read_ubyte(reader)
    return read_string_fixed(reader, length)


def read_matrix(reader):  # 4x4 float matrix
    rows = [read_quartet(reader) for _ in range(4)]
    # TODO: fix axes
    return np.matrix(rows)


blender_axes = True


def fix_axes(ntlet):
    n = len(ntlet)
    assert n == 2 or n == 3 or n == 4

    if n == 2:
        return ntlet[0], -ntlet[1]
    elif n == 3:
        return ntlet[0], ntlet[2], ntlet[1]
    else:
        return ntlet[0], ntlet[1], ntlet[3], ntlet[2]


class MatProps:
    def __init__(self, flags):
        self.UseDiffuseTex = (flags & 0x00040000) != 0

        self.Coloring = (flags & 0x08000000) != 0
        self.MipMapping = (flags & 0x00800000) != 0
        self.TwoSided = (flags & 0x10000000) != 0

        self.AddEffect = (flags & 0x00008000) != 0

        self.ColorKey = (flags & 0x20000000) != 0
        self.AdditiveBlend = (flags & 0x80000000) != 0
        self.UseAlphaTexture = (flags & 0x40000000) != 0

        self.UseEnvTexture = (flags & 0x00080000) != 0
        self.EnvDefaultMode = (flags & 0x00000100) != 0
        self.EnvMultiplyMode = (flags & 0x00000200) != 0
        self.EnvAdditiveMode = (flags & 0x00000400) != 0
        self.EnvYAxisRefl = (flags & 0x00001000) != 0  # is this correct?
        self.EnvYAxisProj = (flags & 0x00002000) != 0
        self.EnvZAxisProj = (flags & 0x00004000) != 0

        self.AnimatedDiffuse = (flags & 0x04000000) != 0
        self.AnimatedAlpha = (flags & 0x02000000) != 0


class Material:
    def __init__(self):
        self.flags = None
        self.matProps = None
        self.ambient_color = None
        self.diffuse_color = None
        self.emission_color = None
        self.alpha = None
        self.metallic = None
        self.filename = None

    def read(self, reader):
        self.flags = read_uint(reader)
        self.matProps = MatProps(self.flags)  # TODO: move to mafia_4ds_import.py

        self.ambient_color = read_triplet(reader)
        self.diffuse_color = read_triplet(reader)
        self.emission_color = read_triplet(reader)
        self.alpha = read_float(reader)

        # env mapping
        if self.matProps.UseEnvTexture:
            self.metallic = read_float(reader)
            self.matProps.envTexture = read_string(reader).lower()
        else:
            self.metallic = 0.0

        # diffuse mapping
        self.filename = read_string(reader).lower()

        # alpha mapping
        if self.matProps.AddEffect and self.matProps.UseAlphaTexture:
            self.matProps.AlphaTexture = read_string(reader).lower()

        # animated texture
        if self.matProps.AnimatedDiffuse:
            self.matProps.AnimatedFrames = read_uint(reader)
            self.matProps.unknown1 = read_ushort(reader)
            self.matProps.AnimFrameLength = read_uint(reader)
            self.matProps.unknown2 = read_ulong(reader)


class Dummy:
    def __init__(self):
        self.aabbMin = None
        self.aabbMax = None

    def read(self, reader):
        self.aabbMin = read_triplet(reader)
        self.aabbMax = read_triplet(reader)

    def write(self, writer):
        raise NotImplementedError()


class Bone:
    def __init__(self):
        self.matrix = None
        self.id = None

    def read(self, reader):
        self.matrix = read_matrix(reader)
        self.id = read_uint(reader)

    def write(self, writer):
        raise NotImplementedError()


class Target:
    def __init__(self):
        self.flags = None
        self.links = []

    def read(self, reader):
        self.flags = read_ushort(reader)
        num_links = read_ubyte(reader)
        self.links = [read_ushort(reader) for _ in range(num_links)]

    def write(self, writer):
        raise NotImplementedError()


frame_types = { # visual frame handled separately
    6: Dummy,
    7: Target,
    10: Bone,
}


class FaceGroup:
    def __init__(self):
        self.material_id = None
        self.faces = None

    def read(self, reader):
        numFaces = read_ushort(reader)
        self.faces = []
        for faceId in range(numFaces):
            face = tuple(read_ushort(reader) for _ in range(3))
            self.faces.append(face)

        self.material_id = read_ushort(reader)

    def write(self, writer):
        raise NotImplementedError()


class Lod:  # level of detail
    def __init__(self):
        self.clipping_range = None
        self.vertices = None
        self.normals = None
        self.uvs = None
        self.face_groups = None

    def read(self, reader):
        self.clipping_range = read_float(reader)
        num_vertices = read_ushort(reader)

        self.vertices = []
        self.normals = []
        self.uvs = []
        for _ in range(num_vertices):
            vertex = read_triplet(reader)
            normal = read_triplet(reader)
            uv = read_doublet(reader)

            if blender_axes:
                vertex = fix_axes(vertex)
                normal = fix_axes(normal)
                uv = fix_axes(uv)

            self.vertices.append(vertex)
            self.normals.append(normal)
            self.uvs.append(uv)

        self.face_groups = []
        num_face_groups = read_ubyte(reader)
        for faceGroupIdx in range(num_face_groups):
            face_group = FaceGroup()
            face_group.read(reader)
            self.face_groups.append(face_group)

    def write(self, writer):
        raise NotImplementedError()


class VertexGroup:
    def read(self, reader):
        pass


class Morph:
    def read(self, reader):
        numTargets = read_ubyte(reader)

        if numTargets > 0:
            numRegions = read_ubyte(reader)
            num_lods = read_ubyte(reader)

            for lodId in range(num_lods):
                for regionIdx in range(numRegions):
                    num_vertices = read_ushort(reader)

                    for vertId in range(num_vertices):
                        for targetIdx in range(numTargets):
                            coord = read_triplet(reader)
                            normal = read_triplet(reader)

                    if numTargets * num_vertices > 0:
                        unknown1 = read_ubyte(reader)

                        if unknown1 == 0:
                            continue

                    for vertId in range(num_vertices):
                        _ = read_ushort(reader)

            dmin = read_triplet(reader)
            dmax = read_triplet(reader)
            origin = read_triplet(reader)
            radius = read_float(reader)


class MeshBone:
    def read(self, reader):
        self.matrix = read_matrix(reader)
        if blender_axes:
            pass  # TODO: Implement fix_axes(matrix)

        self.numLockedVertices = read_uint(reader)  # vertices with weight 1
        self.numWeightedVertices = read_uint(reader)

        self.parent_id = read_uint(reader)

        self.dmin = read_triplet(reader)
        self.dmax = read_triplet(reader)

        self.weights = [read_float(reader) for _ in range(self.numWeightedVertices)]


class Mesh:
    def __init__(self, skin=False, morph=False, billboard=False):
        self.instanceId = None
        self.hasSkin = skin
        self.hasMorph = morph
        self.hasBillboard = billboard

        self.lods = []
        self.armature = None
        self.meshBones = [] # indexed by lod id

    def read(self, reader):
        self.instanceId = read_ushort(reader)
        if self.instanceId > 0:
            return

        num_lods = read_ubyte(reader)
        for lodId in range(num_lods):
            if lodId > 0:
                pass

            lod = Lod()
            lod.read(reader)
            self.lods.append(lod)

        if self.hasSkin:
            for lodId in range(num_lods):
                lodMeshBones = []
                numBones = read_ubyte(reader)
                numLockedVerticesAll = read_uint(reader)  # ???

                dmin = read_triplet(reader)
                dmax = read_triplet(reader)

                for boneId in range(numBones):
                    meshBone = MeshBone()
                    meshBone.read(reader)

        if self.hasMorph:
            self.morph = Morph()
            self.morph.read(reader)

    def write(self, writer):
        raise NotImplementedError()


class VisualFrame:
    def __init__(self, visual_type, render_flags):
        self.visual_type = visual_type
        self.render_flags = render_flags
        self.object = None

    def read(self, reader):
        if self.visual_type == 0x00 or self.visual_type == 0x01:
            self.object = Mesh(skin=False, morph=False, billboard=False)
        elif self.visual_type == 0x02:
            self.object = Mesh(skin=True, morph=False, billboard=False)
        elif self.visual_type == 0x03:
            self.object = Mesh(skin=True, morph=True, billboard=False)
        else:
            raise ValueError('Unknown visual type {}.'.format(self.visual_type))

        self.object.read(reader)

    def write(self, writer):
        raise NotImplementedError()


class Node:
    def __init__(self):
        self.frame = None
        self.parent_id = None
        self.parameters = None
        self.name = None
        self.culling_flags = None
        self.rotation = None
        self.scale = None
        self.location = None
        self.type = None

    def read(self, reader):
        self.type = read_ubyte(reader)

        if self.type == 0x01:  # visual frame
            visual_type = read_ubyte(reader)
            render_flags = read_ushort(reader)

        parent_id = read_ushort(reader)
        self.location = read_triplet(reader)
        self.scale = read_triplet(reader)
        self.rotation = read_quartet(reader)

        if blender_axes:
            self.location = fix_axes(self.location)
            self.scale = fix_axes(self.scale)
            self.rotation = fix_axes(self.rotation)

        self.culling_flags = read_ubyte(reader)
        self.name = read_string(reader)
        print('name: ', self.name, ', type: ',self.type)
        self.parameters = read_string(reader)

        if parent_id > 0:
            self.parent_id = parent_id

        if self.type == 0x01:
            self.frame = VisualFrame(visual_type, render_flags)
            self.frame.read(reader)
        else:
            if self.type not in frame_types:
                raise NotImplementedError('Not implemented frame '.format(self.type))

            self.frame = frame_types[self.type]()
            self.frame.read(reader)

    def write(self, writer):
        raise NotImplementedError()


class FourDSFile:
    def __init__(self):
        self.version = None
        self.timestamp = None

        self.materials = []
        self.nodes = []

    def read(self, reader):
        fourcc = read_string_fixed(reader, 4)
        if fourcc != '4DS\0':
            raise ValueError("Not a 4ds file.")

        self.version = read_ushort(reader)
        if self.version != 0x1d:  # TODO: check other versions
            raise ValueError("Not a Mafia 4ds file.")

        self.timestamp = read_ulong(reader)

        numMaterials = read_ushort(reader)
        for material_idx in range(numMaterials):
            material = Material()
            material.read(reader)
            self.materials.append(material)

        num_nodes = read_ushort(reader)
        for idx in range(num_nodes):
            node = Node()
            node.read(reader)
            self.nodes.append(node)

    def write(self, writer):
        raise NotImplementedError()
