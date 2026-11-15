"""Agrega colision PASIVA a toda malla nueva que aun no tenga cuerpo rigido (bandejas, recipientes, etc.).

No toca los huevos ni nada que ya tenga fisica configurada. Usa los mismos valores que
setup_fisica_ovum1_3.py (margen de 0.5 mm, malla como forma de colision).

Dos formas de usarlo:
  * Dentro de Blender: abrir este archivo en el Text Editor y pulsar Run Script (luego guardar a mano).
    Si hay objetos seleccionados, solo se procesan esos; si no, toda la escena.
  * Por consola: blender --background Ovum1_3.blend --python agregar_colisiones.py -- save
"""
import bpy, sys, json

MARGIN = 0.0005
FRICCION, REBOTE = 0.5, 0.1          # plastico / chapa pintada; espuma o caucho: subir friccion a 0.9
EXCLUIR_PREFIJOS = ("Huevo_", "Cepillo_Cama_", "Cepillo_Superior")
EXCLUIR = {"Cable_Alimentacion", "LED_Rojo", "LED_Verde", "Boton", "Leva_Escape", "Camara_Vision", "Cortinas_Caucho"}

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
sc = bpy.context.scene
vl = bpy.context.view_layer

if sc.rigidbody_world is None:
    bpy.ops.rigidbody.world_add()

def es_proxy(o): return o.name.endswith("_Colision")
candidatos = [o for o in (bpy.context.selected_objects or sc.objects) if o.type == 'MESH']
nuevos = []
for o in candidatos:
    if o.rigid_body or o.name in EXCLUIR or (o.name.startswith(EXCLUIR_PREFIJOS) and not es_proxy(o)):
        continue
    if o.hide_render and not es_proxy(o):
        continue
    for ob in vl.objects: ob.select_set(False)
    o.select_set(True); vl.objects.active = o
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.rigidbody.object_add(type='PASSIVE')
    rb = o.rigid_body
    rb.collision_shape = 'MESH'
    rb.mesh_source = 'FINAL'
    rb.kinematic = bool(o.animation_data and o.animation_data.action)   # si se mueve, que empuje
    rb.friction, rb.restitution = FRICCION, REBOTE
    rb.use_margin = True; rb.collision_margin = MARGIN
    nuevos.append(o.name)

sc.rigidbody_world.point_cache.frame_end = sc.frame_end
if bpy.ops.ptcache.free_bake_all.poll():
    bpy.ops.ptcache.free_bake_all()   # el cache viejo ya no corresponde a la geometria
if "save" in argv:
    bpy.ops.wm.save_mainfile()
print("RESULT " + json.dumps({"colisiones_nuevas": nuevos}))
