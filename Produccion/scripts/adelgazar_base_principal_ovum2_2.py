"""
Ovum2_2: variante DELGADA de BasePrincipal, conservando los retoques hechos a mano.

  1) Guarda de la BasePrincipal actual los retoques del usuario: el relleno bajo la parte delantera de la placa
     (y > -40, entre los postes delanteros y el motor) y la altura del piso del cajon (z 37.39).
  2) Regenera la base con base_principal_rellenable_ovum2_2.py, que ya esta en version delgada:
       - respaldo y orejas de PETG MACIZO de 9 mm (respaldo hasta y -121.01, orejas hasta x -40.34 / 40.77)
       - cemento SOLO en el cajon inferior, que sigue abrazando los postes traseros
       - oreja izq con su agujero de Ø16.06 para el rodamiento, oreja der Ø11.5, sin bujes
       - venteo en (0, -112), llenado en (35, -52), ambos en el piso del cajon
  3) Vuelve a pegar el relleno delantero y recorta el piso a la altura que habia dejado el usuario.

Uso:  blender --background Ovum2_2.blend --python adelgazar_base_principal_ovum2_2.py -- [gruesa|delgada] [save] [render]
      gruesa (por defecto): respaldo y orejas de 16 mm con cemento adentro; delgada: 9 mm macizos, cemento solo abajo
"""
import bpy, bmesh, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene
HERE = os.path.join(os.path.dirname(bpy.data.filepath), "scripts")
MAIN = os.path.join(HERE, "base_principal_rellenable_ovum2_2.py")
m = lambda v: v / 1000.0
Y_FRONT_KEEL = -40.0

def tmp(name, build):
    b = bmesh.new(); build(b)
    me = bpy.data.meshes.new(name); b.to_mesh(me); b.free()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); return o
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
def borrar(*objs):
    for o_ in objs:
        me_ = o_.data; bpy.data.objects.remove(o_, do_unlink=True)
        if me_ and me_.users == 0: bpy.data.meshes.remove(me_)
def medir(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); v = b.calc_volume(signed=True) * 1e6
    nm = sum(1 for e in b.edges if not e.is_manifold); seen = set(); isl = 0
    for f in b.faces:
        if f in seen: continue
        isl += 1; st = [f]; seen.add(f)
        while st:
            g = st.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
    b.free(); return {"vol_cm3": round(v, 1), "cuerpos": isl, "no_manifold": nm}

# 1) retoques del usuario
base = O["BasePrincipal"]
z_piso = min((base.matrix_world @ v.co).z for v in base.data.vertices) * 1000
delantero = base.copy(); delantero.data = base.data.copy(); delantero.name = "_relleno_delantero"; sc.collection.objects.link(delantero)
lim = tmp("_lim", caja(-100, 100, Y_FRONT_KEEL - 1.0, 60, z_piso - 1, 57.5))   # entra 1 mm en el cajon y 0.5 mm en la placa
boolean(delantero, 'INTERSECT', lim); borrar(lim)
rep = {"piso_usuario_z": round(z_piso, 2), "relleno_delantero_original": medir(delantero)}
# el relleno del usuario es de paredes verticales y su malla trae aristas abiertas: se reconstruye limpio como
# prismas a partir de su contorno a media altura (z 47), desde el piso hasta 0.5 mm dentro de la placa
from mathutils.geometry import tessellate_polygon
Z_SEC = (z_piso + 56.95) / 2
b = bmesh.new(); b.from_mesh(delantero.data); b.transform(delantero.matrix_world)
r_ = bmesh.ops.bisect_plane(b, geom=b.verts[:] + b.edges[:] + b.faces[:], plane_co=(0, 0, m(Z_SEC)), plane_no=(0, 0, 1))
cut_e = [e for e in r_["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
adj = {}
for e in cut_e:
    a_, c_ = e.verts; adj.setdefault(a_, []).append(c_); adj.setdefault(c_, []).append(a_)
lazos, vistos = [], set()
for v0 in adj:
    if v0 in vistos: continue
    lazo = [v0]; vistos.add(v0); cur = v0
    while True:
        nx = [w for w in adj[cur] if w not in vistos]
        if not nx: break
        cur = nx[0]; vistos.add(cur); lazo.append(cur)
    if len(lazo) >= 3: lazos.append([Vector((v.co.x, v.co.y)) for v in lazo])
b.free(); borrar(delantero)
def area(p): return 0.5 * sum(p[i].x * p[(i + 1) % len(p)].y - p[(i + 1) % len(p)].x * p[i].y for i in range(len(p)))
lazos = [l if area(l) > 0 else list(reversed(l)) for l in lazos if abs(area(l)) > 1e-6]   # > 1 mm2
def adentro(poly, d):
    """contorno d metros hacia adentro: sin caras coplanares con los bordes de la placa (el boolean une limpio)"""
    out = []; n = len(poly)
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        e1 = (p1 - p0); e2 = (p2 - p1)
        if e1.length < 1e-9 or e2.length < 1e-9: continue
        e1.normalize(); e2.normalize()
        a_ = p1 + Vector((-e1.y, e1.x)) * d; c_ = p1 + Vector((-e2.y, e2.x)) * d
        den = e1.x * e2.y - e1.y * e2.x
        if abs(den) < 1e-6: out.append(a_); continue
        t = ((c_.x - a_.x) * e2.y - (c_.y - a_.y) * e2.x) / den
        out.append(a_ + e1 * t)
    return out
lazos = [adentro(l, m(0.02)) for l in lazos]
def prismas(b):
    for l in lazos:
        tris = tessellate_polygon([[(p.x, p.y, 0.0) for p in l]])
        vb = [b.verts.new((p.x, p.y, m(z_piso - 1.0))) for p in l]; vt = [b.verts.new((p.x, p.y, m(57.5))) for p in l]
        for t in tris:
            b.faces.new([vt[t[0]], vt[t[1]], vt[t[2]]]); b.faces.new([vb[t[2]], vb[t[1]], vb[t[0]]])
        for k in range(len(l)): b.faces.new((vb[k], vb[(k + 1) % len(l)], vt[(k + 1) % len(l)], vt[k]))
delantero = tmp("_relleno_delantero", prismas)
rep["relleno_delantero"] = medir(delantero); rep["relleno_delantero_contornos"] = len(lazos)

# 2) regenerar con el script principal (sin guardar ni renderizar desde alli)
_argv = sys.argv; sys.argv = [sys.argv[0], "--", "delgada" if "delgada" in argv else "gruesa"]
try:
    exec(compile(open(MAIN, encoding="utf-8").read(), MAIN, "exec"), {"__name__": "__main__"})
finally:
    sys.argv = _argv
base = O["BasePrincipal"]; cem = O["BasePrincipal_Cemento"]

# 3) pegar el relleno delantero y recortar el piso
boolean(base, 'UNION', delantero); borrar(delantero)
piso = tmp("_piso", caja(-80, 90, -150, 50, 20, z_piso)); boolean(base, 'DIFFERENCE', piso); borrar(piso)   # el relleno baja 1 mm de mas
base.data.polygons.foreach_set("use_smooth", [False] * len(base.data.polygons)); base.data.update()
rep["base"] = medir(base); rep["cemento"] = medir(cem)
print("ADELGAZAR", rep)
if "save" in argv: bpy.ops.wm.save_mainfile(); print("GUARDADO", bpy.data.filepath)

if "render" in argv:
    OUT = os.path.join(os.path.dirname(bpy.data.filepath), "renders", "BasePrincipal_" + ("Delgada" if "delgada" in argv else "Gruesa")); os.makedirs(OUT, exist_ok=True)
    ins = O.get("BasePrincipal_Insertos")
    r = sc.render; r.engine = 'BLENDER_WORKBENCH'; r.resolution_x, r.resolution_y = 1600, 1200
    sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_cavity = True; sh.show_object_outline = True
    cam = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.lens = 60
    tgt = Vector((m(5), m(-50), m(85)))
    def shot(fn, d, objs, dist=0.5):
        for o in O:
            if o.type == 'MESH': o.hide_render = o not in objs
        d = Vector(d).normalized(); cam.location = tgt + d * dist; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        r.filepath = os.path.join(OUT, fn); bpy.ops.render.render(write_still=True); print("RENDER", r.filepath)
    vis = [base] + ([ins] if ins else [])
    shot("01_iso_frente.png", (1.0, 1.3, 0.8), vis)
    shot("02_iso_atras.png", (-1.1, -1.4, 0.7), vis)
    shot("03_abajo.png", (0.7, 0.9, -1.0), vis)
    def corte(fn, c, d, dist=0.5):
        cuts = []
        for o in [base, cem] + ([ins] if ins else []):
            k = o.copy(); k.data = o.data.copy(); sc.collection.objects.link(k); cuts.append(k)
        cut = tmp("_c", caja(*c)); cut.hide_render = True
        for k in cuts:
            md = k.modifiers.new("c", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.solver = 'EXACT'; md.object = cut
        shot(fn, d, cuts, dist)
        borrar(*cuts, cut)
    corte("04_corte_x0_centro.png", (-100, 0, -200, 100, 0, 200), (-1.0, 0.3, 0.3))
    corte("05_corte_y-100_orejas.png", (-100, 100, -100, 100, 0, 200), (0.3, 1.0, 0.35))
    corte("06_corte_z47_planta.png", (-100, 100, -200, 100, 46.95, 200), (0.15, 0.25, 1.0), 0.45)
