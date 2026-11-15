"""
Ovum2_2: correccion del eje en BasePrincipal (rellenable con cemento). Trabaja sobre la BasePrincipal ACTUAL,
respetando los retoques hechos a mano (no la regenera).

  - Sin bujes: se ocultan PETG_Buje_Izq / PETG_Buje_Der.
  - Oreja izquierda (lado SIN servo): lleva rodamiento. Se recupera su agujero original de Ø16.06 (el engrosamiento
    lo invadia por abajo y por el lado del respaldo) y la zona gruesa de esa oreja baja a z 115.
  - Alrededor del agujero se devuelve plastico macizo (pared >= 3 mm hasta el cemento) y se descuenta del cemento.
  - Oreja derecha (lado del servo): queda con Ø11.5, como estaba.

Uso (recomendado, con el archivo abierto): pestaña Scripting > Open > este archivo > Run Script; despues guardar.
     o: blender --background Ovum2_2.blend --python eje_rodamiento_base_principal_ovum2_2.py -- [save]
"""
import bpy, bmesh, math, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene
EJE_Y, EJE_Z = -105.47, 123.79
D_ROD = 16.06                  # agujero original de la oreja izquierda (rodamiento)
WALL = 3.0
X_IZQ = (-60.0, -29.0)         # tramo del corte: toda la oreja izquierda engrosada (x -48.2 .. -31.34)
Z_THICK_L = 115.0              # nuevo tope de la zona gruesa de la oreja izquierda (agujero desde z 115.76)
m = lambda v: v / 1000.0

base = O["BasePrincipal"]; cem = O.get("BasePrincipal_Cemento")
rep = {}

def tmp(name, build):
    b = bmesh.new(); build(b)
    me = bpy.data.meshes.new(name); b.to_mesh(me); b.free()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); return o
def cyl_x(r, x0, x1, seg=64):
    def f(b):
        g = bmesh.ops.create_cone(b, cap_ends=True, segments=seg, radius1=m(r), radius2=m(r), depth=m(x1 - x0))
        bmesh.ops.rotate(b, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(Vector((1, 0, 0))).to_matrix())
        bmesh.ops.translate(b, verts=g['verts'], vec=(m((x0 + x1) / 2), m(EJE_Y), m(EJE_Z)))
    return f
def caja(x0, x1, y0, y1, z0, z1):
    def f(b):
        g = bmesh.ops.create_cube(b, size=1.0)
        bmesh.ops.scale(b, verts=g['verts'], vec=(m(x1 - x0), m(y1 - y0), m(z1 - z0)))
        bmesh.ops.translate(b, verts=g['verts'], vec=(m((x0 + x1) / 2), m((y0 + y1) / 2), m((z0 + z1) / 2)))
    return f
def boolean(obj, op, operand):
    md = obj.modifiers.new("b", 'BOOLEAN'); md.operation = op; md.solver = 'EXACT'; md.object = operand; md.use_self = True
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    obj.modifiers.remove(md); old = obj.data
    me.materials.clear()
    for mt in old.materials: me.materials.append(mt)
    obj.data = me
    if old.users == 0: bpy.data.meshes.remove(old)
def vol(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); v = b.calc_volume(signed=True) * 1e6
    nm = sum(1 for e in b.edges if not e.is_manifold); b.free(); return round(v, 1), nm
rep["antes"] = {"base": vol(base), "cemento": vol(cem) if cem else None}

# 1) pared maciza alrededor del rodamiento: lo que el cemento ocupa a menos de r+WALL pasa a ser plastico
if cem:
    anillo = tmp("_anillo", cyl_x(D_ROD / 2 + WALL, *X_IZQ))
    pieza = cem.copy(); pieza.data = cem.data.copy(); sc.collection.objects.link(pieza)
    boolean(pieza, 'INTERSECT', anillo)
    if len(pieza.data.polygons):
        boolean(base, 'UNION', pieza)
        boolean(cem, 'DIFFERENCE', anillo)
    rep["cemento_pasado_a_plastico_cm3"] = vol(pieza)[0] if len(pieza.data.polygons) else 0.0
    for o_ in (anillo, pieza):
        me_ = o_.data; bpy.data.objects.remove(o_, do_unlink=True); bpy.data.meshes.remove(me_)
# 2) baja la zona gruesa de la oreja izq a z 115 (solo por fuera de la oreja, delante del respaldo) y corta el Ø16.06
recorte = tmp("_recorte", caja(-60.0, -35.34, -112.01, -92.0, Z_THICK_L, Z_THICK_L + 1.2))
boolean(base, 'DIFFERENCE', recorte)
agujero = tmp("_agujero", cyl_x(D_ROD / 2, *X_IZQ))
boolean(base, 'DIFFERENCE', agujero)
for o_ in (recorte, agujero):
    me_ = o_.data; bpy.data.objects.remove(o_, do_unlink=True); bpy.data.meshes.remove(me_)
# 3) sin bujes
for n in ("PETG_Buje_Izq", "PETG_Buje_Der"):
    if O.get(n): O[n].hide_set(True); O[n].hide_render = True
rep["despues"] = {"base": vol(base), "cemento": vol(cem) if cem else None}
print("EJE_RODAMIENTO", rep)
if "save" in argv: bpy.ops.wm.save_mainfile(); print("GUARDADO", bpy.data.filepath)
