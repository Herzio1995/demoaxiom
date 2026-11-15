"""
Ovum2_0: rehace los pivotes (tetones) de las almohadillas de silicona para que atraviesen la banda del soporte
tal como esta ahora (el usuario engroso ~3 mm la banda por debajo y los pivotes viejos quedaban cortos: la
cabeza conica quedaba dentro del plastico).

  - Regenera el cuerpo de cada almohadilla SIN pivotes con silicona_pesador_ovum1_9.py (mismo resultado que el
    original), dejando intactos los soportes del usuario.
  - Vastago de 3.4 mm desde dentro de la almohadilla hasta 1.2 mm bajo la banda; cabeza conica de 5.4 mm
    paralela a la cara inferior de la banda, 0.2 mm por debajo de ella.
  - No toca los soportes ni la cara superior de la silicona.

Uso:  blender --background <archivo>.blend --python alargar_tetones_ovum2_0.py
      (o exec(...) dentro de Blender). Deja el resultado en la variable `report`.
"""
import bpy, bmesh, json, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

O = bpy.data.objects
PEG_D = 0.0034                     # = agujero del soporte
HEAD_D, HEAD_L, HEAD_TIP = 0.0054, 0.0026, 0.0014
PIEZAS = {
    "pesador": dict(DST="PesadorSoporteSilicona", PAD="Silicona_Pesador_", X=0.0214, PEG_Y=(-0.0850, -0.0660)),
    "girador": dict(DST="SoporteGiradorSilicona", PAD="Silicona_Girador_", X=0.0202, PEG_Y=(-0.0220, -0.0030)),
}
report = {}

def tree_of(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
def link_tmp(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o); return o
def drop(o):
    me = o.data; bpy.data.objects.remove(o, do_unlink=True)
    if me and me.users == 0: bpy.data.meshes.remove(me)
def boolean(target, operand, op, self_=False):
    m = target.modifiers.new("b_" + op.lower(), 'BOOLEAN'); m.operation = op; m.object = operand; m.solver = 'EXACT'
    m.use_self = self_
    with bpy.context.temp_override(object=target, active_object=target):
        bpy.ops.object.modifier_apply(modifier=m.name)
def dos_contactos(t, x, y):
    """desde arriba: (1er contacto, 2o contacto) = cara superior e inferior de la primera capa"""
    h1 = t.ray_cast(Vector((x, y, 0.3)), Vector((0, 0, -1)))[0]
    h2 = t.ray_cast(h1 - Vector((0, 0, 1e-6)), Vector((0, 0, -1)))[0] if h1 else None
    return h1, h2
ANILLO = [(math.cos(a), math.sin(a)) for a in [k * math.pi / 4 for k in range(8)]]

import os, sys
_dir = os.path.join(os.path.dirname(bpy.data.filepath), "scripts")
if not os.path.isdir(_dir): _dir = r"G:\My Drive\TILINKA GENERAL\Tilinka Hardworks\Ovum Machine\scripts"
for PZ, C in PIEZAS.items():
    # los soportes del usuario se apartan mientras el script viejo genera los cuerpos (crea su propio soporte)
    usr = O[C["DST"]]; usr.name = C["DST"] + "_usuario"; usr_data = usr.data.name
    argv0 = sys.argv; sys.argv = ["blender", "--", f"pieza={PZ}", "sin_pivotes"]
    try:
        exec(open(os.path.join(_dir, "silicona_pesador_ovum1_9.py"), encoding="utf-8").read(), {"__name__": "cuerpos"})
    finally:
        sys.argv = argv0
    drop(O[C["DST"]]); usr.name = C["DST"]; usr.data.name = usr_data
for PZ, C in PIEZAS.items():
    dst = O[C["DST"]]; tsup = tree_of(dst)
    for side in (-1, 1):
        po = O[C["PAD"] + ("Izq" if side < 0 else "Der")]
        x = side * C["X"]; info = []
        # ---------------------------------------------- medidas (antes de tocar nada)
        tp = tree_of(po); medidas = []
        for y in C["PEG_Y"]:
            fondo = [dos_contactos(tp, x + 0.0032 * c, y + 0.0032 * s)[1] for c, s in ANILLO]    # fondo de la silicona
            zp = sum(p.z for p in fondo) / len(fondo)
            pts = []
            for dx, dy in ((0.0026, 0), (0, 0.0026), (-0.0026, 0), (0, -0.0026)):          # cara inferior de la banda
                pts.append(dos_contactos(tsup, x + dx, y + dy)[1])
            zb = sum(p.z for p in pts) / 4
            medidas.append((y, zp, zb, pts))
        # ---------------------------------------------- pivotes nuevos
        pb = bmesh.new()
        for y, zp, zb, pts in medidas:
            z_top = zp + 0.0008; z_bot = zb - 0.0012
            g = bmesh.ops.create_cone(pb, cap_ends=True, segments=24, radius1=PEG_D / 2, radius2=PEG_D / 2, depth=z_top - z_bot)
            bmesh.ops.translate(pb, verts=g['verts'], vec=(x, y, (z_top + z_bot) / 2))
            P0 = sum(pts, Vector()) / 4
            u = (pts[0] - pts[2]).cross(pts[1] - pts[3]).normalized()
            if u.z < 0: u = -u
            g = bmesh.ops.create_cone(pb, cap_ends=True, segments=24, radius1=HEAD_TIP, radius2=HEAD_D / 2, depth=HEAD_L)
            bmesh.ops.rotate(pb, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(u).to_matrix())
            bmesh.ops.translate(pb, verts=g['verts'], vec=P0 - u * (0.0002 + HEAD_L / 2))
            info.append({"y_mm": round(y * 1000, 1), "vastago_mm": round((zp - zb) * 1000, 2),
                         "inclinacion_cabeza_grados": round(math.degrees(u.angle(Vector((0, 0, 1)))), 1)})
        pg = link_tmp("tmp_pivotes", pb); boolean(po, pg, 'UNION', self_=True); drop(pg)
        # ---------------------------------------------- revision
        b = bmesh.new(); b.from_mesh(po.data); b.transform(po.matrix_world); b.normal_update()
        manifold = all(e.is_manifold for e in b.edges); vol = round(b.calc_volume() * 1e6, 2)
        for v in b.verts: v.co -= v.normal * 0.00005
        choca = bool(BVHTree.FromBMesh(b).overlap(tsup)); b.free()
        tp = tree_of(po)
        punta = [round(tp.ray_cast(Vector((x, y, 0.0)), Vector((0, 0, 1)))[0].z * 1000, 2) for y in C["PEG_Y"]]
        report[po.name] = {"pivotes": info, "punta_z_mm": punta, "banda_inferior_z_mm": [round(m[2] * 1000, 2) for m in medidas],
                           "manifold": manifold, "vol_cm3": vol, "choca_con_soporte": choca}
print("RESULT " + json.dumps(report))
