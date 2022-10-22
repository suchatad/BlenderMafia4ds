import bpy
import bmesh
import os
import time
from mathutils import Matrix, Vector

from bpy import ops
from bpy import path
from bpy import props
from bpy import types
from bpy import utils
from bpy_extras import io_utils
from bpy_extras import node_shader_utils
from bpy_extras import image_utils

from . import parse_4ds as FourDS
from . import parse_5ds as FiveDS


def blen_load_image(filepath: str):
    image = image_utils.load_image(
        filepath,
        place_holder=True,
        check_existing=True,
    )
    return image


def blen_create_material(material: FourDS.Material):
    bma = bpy.data.materials.new(material.diffuse_texture)
    bma_wrap = node_shader_utils.PrincipledBSDFWrapper(bma, is_readonly=False, use_nodes=True)

    bma_wrap.alpha = material.alpha
    bma_wrap.metallic = material.metallic
    bma_wrap.specular = 0.0
    bma_wrap.roughness = 0.0

    texture_wrapper = bma_wrap.base_color_texture

    filepath = '{}maps/{}'.format(GetPreferences().DataPath, material.diffuse_texture)
    diffuse_image = blen_load_image(filepath)
    texture_wrapper.image = diffuse_image

    if material.has_effect:
        assert not (material.alpha_texture and material.use_alpha_color)  # hopefully this won't happen

        if material.alpha_texture:
            alpha_image = blen_load_image(material.alpha_texture)
            bma_wrap.alpha_texture.image = alpha_image
        elif material.use_alpha_color:
            # not every color key is black !!!!
            # this doesn't work on those that are not
            # todo: make it work
            bma.blend_method = 'CLIP'

            # rgb = diffuse_image.pixels[:3]  # color of the corner pixel
            # print("pixels", rgb)

            color_ramp = bma.node_tree.nodes.new("ShaderNodeValToRGB")
            color_ramp.color_ramp.elements[1].position = 1e-5

            bma.node_tree.links.new(texture_wrapper.node_image.outputs["Color"], color_ramp.inputs["Fac"])
            bma.node_tree.links.new(color_ramp.outputs["Color"], bma_wrap.node_principled_bsdf.inputs["Alpha"])

    return bma


class BoneObject:  # placeholder for bones in the objects list
    def __init__(self):
        self.name = None


class FourDSImporter:
    node_handlers = {}

    def __init__(self, filepath):
        self.filepath = filepath
        self.fo = None

        self.file_collection = None
        self.dummy_collection = None

        self.materials = []

        self.objects = []  # indexed by node id, only the first lod
        self.object_map = {}  # indexed by node name, list of objects belonging to a node

        self.armature_obj = None
        self.armature_scale_factor = None
        self.base_id = None

    def parent_to_bone(self, obj, bone_name):
        # simplest way to properly parent object to a bone is through operators
        bpy.ops.object.select_all(action='DESELECT')
        self.armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = self.armature_obj

        bpy.ops.object.mode_set(mode='EDIT')
        edit_bone = self.armature_obj.data.edit_bones[bone_name]
        self.armature_obj.data.edit_bones.active = edit_bone
        bone_matrix = Matrix(edit_bone.matrix)

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        obj.select_set(True)
        self.armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = self.armature_obj

        bone_matrix_tr = Matrix.Translation(bone_matrix.to_translation())  # cut out the rotation part
        obj.matrix_basis = self.armature_obj.parent.matrix_world @ bone_matrix_tr @ obj.matrix_basis

        bpy.ops.object.parent_set(type='BONE')

    def apply_transform(self, node, obj):
        obj.location = node.location
        obj.scale = node.scale
        obj.rotation_mode = 'QUATERNION'
        obj.rotation_quaternion = node.rotation

        if node.parent_id > 0:
            parent_obj = self.objects[node.parent_id - 1]
            if isinstance(parent_obj, bpy.types.Object):
                obj.parent = parent_obj
            elif isinstance(parent_obj, BoneObject):
                self.parent_to_bone(obj, parent_obj.name)
            else:
                raise RuntimeError()

    def create_meshobject(self, name, indexed=True, collection=None):
        me = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, me)

        if not collection:
            collection = self.file_collection
        collection.objects.link(obj)

        if indexed:
            self.objects.append(obj)

        return me, obj

    def handle_general(self, node):
        me, obj = self.create_meshobject(node.name)
        self.apply_transform(node, obj)
        return [obj]

    def handle_bone(self, node):
        # this one is tricky
        # 4ds treats every bone as a separate object with its own set of transformation
        # blender handles bones within a single armature object
        # for object orientation of the local axes comes from its transformation matrix
        # for bones Y axis is a vector from head to tail, X and Z depend on the bone roll

        bone_id = node.frame.id
        bone_matrix = Matrix(node.frame.matrix)

        # if there's no armature, make one
        if not self.armature_obj:
            armature = bpy.data.armatures.new('Armature')
            armature.display_type = 'STICK'
            self.armature_obj = bpy.data.objects.new('Armature', armature)
            self.armature_obj.show_in_front = True
            self.file_collection.objects.link(self.armature_obj)

            bpy.context.view_layer.objects.active = self.armature_obj
            bpy.ops.object.mode_set(mode='EDIT')
            base_bone = armature.edit_bones.new('base')
            base_bone.tail = (0, 0, 0)
            base_bone.head = (0, -0.3, 0)  # arbitrary

            self.base_id = node.parent_id
            self.armature_obj.parent = self.objects[self.base_id - 1]  # affected mesh
        else:
            armature = self.armature_obj.data
            bpy.context.view_layer.objects.active = self.armature_obj
            bpy.ops.object.mode_set(mode='EDIT')

        bone = armature.edit_bones.new(node.name)

        bo = BoneObject()
        bo.name = node.name
        self.objects.append(bo)

        # another (potential?) problem is bone scaling
        # scale factors other than 1.0 seem to appear only on root bones of skeletal branches
        # they also tend to be the same
        # if that's the case we can simply scale the entire armature with a common scale factor
        # otherwise it's a little bit more complicated todo: check if this can actually happen
        if node.parent_id == self.base_id:
            bone.parent = armature.edit_bones['base']
            bone.head = node.location
            if self.armature_scale_factor:
                if self.armature_scale_factor != node.scale:
                    raise NotImplementedError('Non-uniform armature scaling is not implemented.')
            else:
                self.armature_scale_factor = node.scale

        else:
            if node.scale != (1.0, 1.0, 1.0):
                raise NotImplementedError('Non-uniform armature scaling is not implemented.')

            parent_name = self.fo.nodes[node.parent_id-1].name
            bone.parent = armature.edit_bones[parent_name]
            bone.head = Vector(node.location) + bone.parent.head

        # bones in 4ds format come with transformation matrices defining default rotation and scale (rest pose)
        # there is some ambiguity in how to interpret them since their effect depends on the orientation of unit bone
        # they act on, ultimately this won't influence animations and doesn't really matter
        bone.tail = bone.head + bone_matrix @ Vector((0, 1, 0))

        # switch back to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        return [bo]

    def handle_dummy(self, node):
        me, obj = self.create_meshobject(node.name, collection=self.dummy_collection)
        self.apply_transform(node, obj)

        # create axis aligned cuboid
        diagonal = [b - a for a, b in zip(node.frame.min, node.frame.max)]
        diagonal.append(1.0)
        mat = Matrix.Diagonal(diagonal)

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1, matrix=mat)
        bm.to_mesh(me)
        bm.free()

        # make it pretty
        obj.display_type = 'WIRE'
        obj.show_name = True
        return [obj]

    def handle_visual_frame(self, node):
        lod_objects = []
        for lod_id, lod in enumerate(node.frame.object.lods):
            if lod_id == 0:
                indexed = True
                name = node.name
            else:
                indexed = False
                name = '{}_lod{}'.format(node.name, lod_id)

            me, obj = self.create_meshobject(name, indexed=indexed)
            self.apply_transform(node, obj)
            lod_objects.append(obj)

            # build mesh
            all_faces = []
            material_ids = []
            for face_group in lod.face_groups:
                all_faces.extend(face_group.faces)
                material_ids.extend([face_group.material_id] * len(face_group.faces))

            me.from_pydata(lod.vertices, [], all_faces)

            # set up normals
            me.flip_normals()
            me.normals_split_custom_set_from_vertices(lod.normals)
            me.use_auto_smooth = True

            # set up uv layer
            uv_layer = me.uv_layers.new(do_init=False)
            for poly in me.polygons:
                for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    vertex_index = me.loops[loop_index].vertex_index
                    uv_layer.data[loop_index].uv = lod.uvs[vertex_index]

            slot_dict = {}  # maps material_id to slot_id
            for slot_id, face_group in enumerate(lod.face_groups):
                bpy.ops.object.material_slot_add({"object": obj})
                material_id = face_group.material_id
                slot_dict[material_id] = slot_id
                material_slot = obj.material_slots[slot_id]
                material_slot.material = self.materials[material_id - 1]

            for face, material_id in zip(me.polygons, material_ids):
                face.material_index = slot_dict[material_id]

            # set up blender vertex groups
            # vertex groups defined in a 4ds file are always disjoint
            # this means that each vertex can be influenced by only one bone
            # keep this in mind when creating in-game models
            vertex_groups = node.frame.object.vertex_groups
            if vertex_groups:
                # bone nodes indexed by bone id
                bone_nodes = dict((node.frame.id, node) for node in self.fo.nodes if node.type == 10)
                num_bones = len(bone_nodes)
                lod_vertex_groups = vertex_groups[lod_id*num_bones:(lod_id+1)*num_bones]

                vertex_counter = 0
                for bone_id, vertex_group in enumerate(lod_vertex_groups):
                    bone_node = bone_nodes[bone_id]
                    bvg = obj.vertex_groups.new(name=bone_node.name)

                    # sets all weights to 1
                    locked_vertices = list(range(vertex_counter, vertex_group.num_locked_vertices +
                                                 len(vertex_group.weights) + vertex_counter))
                    vertex_counter += vertex_group.num_locked_vertices + len(vertex_group.weights)
                    bvg.add(locked_vertices, 1.0, 'ADD')

                # lock remaining vertices to the base bone
                base_vg = obj.vertex_groups.new(name='base')
                base_vertices = list(range(vertex_counter, len(lod.vertices)))
                base_vg.add(base_vertices, 1.0, 'ADD')

            # hide secondary lods
            if lod_id > 0:
                obj.hide_set(True)  # obj.hide_viewport broken?
                obj.hide_render = True

        return lod_objects

    def handle_node(self, node: FourDS.Node):
        if node.type in FourDSImporter.node_handlers:
            handler = FourDSImporter.node_handlers[node.type]
            objs = handler(self, node)
        else:
            objs = self.handle_general(node)
            ShowWarning("Skipping node {} of unimplemented type {}".format(node.name, node.type))

        self.object_map[node.name] = objs

    def import_file(self):
        with open(self.filepath, "rb") as f:
            self.fo = FourDS.FourDSFile()
            self.fo.read(f)

        # create and link collections
        filename = os.path.basename(self.filepath)
        self.file_collection = bpy.data.collections.new(filename)
        self.dummy_collection = bpy.data.collections.new("Dummy objects")
        bpy.context.scene.collection.children.link(self.file_collection)
        self.file_collection.children.link(self.dummy_collection)

        # load materials and handle nodes
        self.materials = [blen_create_material(mo) for mo in self.fo.materials]
        for node in self.fo.nodes:
            self.handle_node(node)

        # set up the armature
        if self.armature_obj:
            base_name = self.fo.nodes[self.base_id - 1].name
            base_objects = self.object_map[base_name]

            # add a modifier for every lod
            for base_object in base_objects:
                arm_mod = base_object.modifiers.new(self.armature_obj.name, 'ARMATURE')
                arm_mod.object = self.armature_obj

            # scale by common scale factor
            self.armature_obj.scale = self.armature_scale_factor


FourDSImporter.node_handlers = {
    1: FourDSImporter.handle_visual_frame,
    6: FourDSImporter.handle_dummy,
    10: FourDSImporter.handle_bone,
}


class Mafia4ds_ImportDialog(types.Operator, io_utils.ImportHelper):
    "Import Mafia 4ds model."
    bl_idname = "mafia4ds.import_"
    bl_text = "Mafia (.4ds)"
    bl_label = "Import 4DS"
    filename_ext = ".4ds"

    filter_glob: props.StringProperty(
        default="*.4ds",
        options={"HIDDEN"},
        maxlen=255
    )

    def execute(self, context):
        if len(GetPreferences().DataPath) == 0:
            ShowError("No game data path set!\n"
                      "\n"
                      "Go into Edit -> Preferences -> Addons,\n"
                      "search for Mafia 4ds addon, expand it,\n"
                      "click to Game Data Path selector\n"
                      "and choose appropriate directory.")

            return {'CANCELLED'}

        importer = FourDSImporter(self.filepath)
        try:
            importer.import_file()
        except ValueError as ve:
            print(ve)
            ShowError(ve)
            return {'CANCELLED'}

        return {'FINISHED'}


def ShowError(message):
    def draw(self, context):
        print(message)

        for line in message.split("\n"):
            self.layout.label(text=line)

    bpy.context.window_manager.popup_menu(draw, title="Error", icon="ERROR")


def ShowWarning(message):
    print(message)


def GetPreferences():
    globalPreferences = bpy.context.preferences
    addonPreferences = globalPreferences.addons[__package__].preferences

    return addonPreferences


def MenuImport(self, context):
    self.layout.operator(Mafia4ds_ImportDialog.bl_idname, text=Mafia4ds_ImportDialog.bl_text)


def register():
    utils.register_class(Mafia4ds_ImportDialog)
    types.TOPBAR_MT_file_import.append(MenuImport)


def unregister():
    utils.unregister_class(Mafia4ds_ImportDialog)
    types.TOPBAR_MT_file_import.remove(MenuImport)


if __name__ == "__main__":
    register()

    ops.mafia4ds.import_('INVOKE_DEFAULT')
