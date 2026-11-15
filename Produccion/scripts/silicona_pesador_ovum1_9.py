"""
Ovum1_9: almohadillas de silicona para el pesador (sujetador del huevo) "PesadorPreSilicona".

Diseno
  - Una almohadilla por pared que cubre TODA su cara superior (meseta trasera, arco y subida al poste delantero).
    Su cara superior ES la superficie actual, asi el huevo queda en la misma posicion.
  - Soporte ("PesadorSoporteSilicona", copia del original): toda esa cara se rebaja T = 2 mm hacia dentro; la
    almohadilla envuelve la pared de punta a punta siguiendo la curva, asi se ubica sola.
  - Retencion sin pegamento: cada almohadilla tiene 2 pivotes con cabeza conica (tipo pata de goma) que pasan por
    agujeros de 2.6 mm en la banda del arco y asoman a la ventana de abajo: se empuja y se tira de la cabeza.
  - El original queda oculto como respaldo. Se exportan STL en mm a la carpeta stl/.

Piezas (argumento pieza=...):
  pesador (por defecto): PesadorPreSilicona -> PesadorSoporteSilicona + Silicona_Pesador_Izq/Der
  girador              : SoporteGiradorPETG -> SoporteGiradorSilicona + Silicona_Girador_Izq/Der

Uso:  blender --background Ovum1_9.blend --python silicona_pesador_ovum1_9.py [-- pieza=girador] [save]
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects
PIEZAS = {
    "pesador": dict(SRC="PesadorPreSilicona", DST="PesadorSoporteSilicona", PAD="Silicona_Pesador_",
                    X_IN=0.0150, X_OUT=0.0278, Y0=-0.0995, Y1=-0.0425, PEG_Y=(-0.0850, -0.0660), BORDES="ejes"),
    "girador": dict(SRC="SoporteGiradorPETG", DST="SoporteGiradorSilicona", PAD="Silicona_Girador_",
                    X_IN=0.0150, X_OUT=0.0253, Y0=-0.0430, Y1=0.0180, PEG_Y=(-0.0220, -0.0030), BORDES="vertical"),
}
PZ = next((a.split("=")[1] for a in argv if a.startswith("pieza=")), "pesador")
CFG = PIEZAS[PZ]
SRC, DST, PAD = CFG["SRC"], CFG["DST"], CFG["PAD"]
T = 0.0030                 # espesor de la silicona (= rebaje); 2 mm en Ovum1_9 quedaba delgada
HOLE_D = 0.0034            # agujero en el soporte (2.6 mm en Ovum1_9: los pivotes no se llenaban)
PEG_D = 0.0034             # vastago del pivote (= agujero: la silicona sella)
HEAD_D, HEAD_L = 0.0054, 0.0026   # cabeza conica del pivote
PEG_Y = CFG["PEG_Y"]               # posicion de los pivotes a lo largo del arco
X_IN, X_OUT = CFG["X_IN"], CFG["X_OUT"]   # bordes de la franja superior (|x|)
EPS = 2e-4
report = {"avisos": [], "pieza": PZ}

src = O[SRC]
# ---------------------------------------------------------------- limpiar corridas anteriores
for n in [DST, PAD + "Izq", PAD + "Der", "tmp_agujeros", "tmp_pivotes"]:
    if O.get(n):
        me = O[n].data; bpy.data.objects.remove(O[n], do_unlink=True)
        if me and me.users == 0: bpy.data.meshes.remove(me)

dst = src.copy(); dst.data = src.data.copy(); dst.name = DST; dst.data.name = DST
for c in src.users_collection: c.objects.link(dst)
src.hide_set(True); src.hide_render = True

def mat(name, col, rough=0.5, alpha=1.0):
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*col, 1); b.inputs["Roughness"].default_value = rough
    if alpha < 1: b.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*col, alpha); return m
M_SIL = mat("Silicona_Shore40", (0.35, 0.65, 0.95), 0.6, 0.9)
M_SOP = mat("PETG_Pesador", (0.82, 0.82, 0.84), 0.45)
if not dst.data.materials or dst.data.materials[0] is None:
    dst.data.materials.clear(); dst.data.materials.append(M_SOP)

# ---------------------------------------------------------------- cara superior completa de cada pared
# Todas las caras que miran hacia arriba en lo alto de cada pared (meseta trasera, arco y subida al poste
# delantero) forman un parche. La almohadilla es ese parche + su copia desplazada T hacia dentro de la pieza;
# el soporte baja esos mismos vertices T. Los vertices del borde solo se mueven dentro del plano de su cara
# lateral/extremo, asi esas caras siguen planas y la almohadilla queda a ras con ellas.
mw = dst.matrix_world.copy()
bm = bmesh.new(); bm.from_mesh(dst.data); bm.transform(mw); bm.normal_update()
Y0, Y1 = CFG["Y0"], CFG["Y1"]
def patch(side):
    return [f for f in bm.faces if f.normal.z > 0.4 and all(q.co.z > 0.155 and X_IN - EPS <= side * q.co.x <= X_OUT + EPS
            and Y0 <= q.co.y <= Y1 for q in f.verts)]

def offsets(F):
    """desplazamiento de cada vertice del parche (hacia dentro de la pieza)"""
    Fs = set(F); out = {}; worst = 1.0
    for v in {q for f in F for q in f.verts}:
        nv = sum((f.normal for f in v.link_faces if f in Fs), Vector()).normalized()
        cons = []
        for f in v.link_faces:
            if f in Fs or f.calc_area() < 1e-12: continue
            c = f.normal.normalized()
            if CFG.get("BORDES", "ejes") == "ejes" and max(abs(c.x), abs(c.y), abs(c.z)) < 0.98: continue
            if all(abs(c.dot(k)) < 0.995 for k in cons): cons.append(c)
        if CFG.get("BORDES") == "vertical":
            # todo baja en vertical: la silueta en planta no cambia y las caras laterales/remates siguen planos;
            # la profundidad compensa la inclinacion para que el espesor normal sea T
            d = Vector((0, 0, 1)); k = max(nv.z, 0.5)
            worst = min(worst, nv.z); out[v] = d * (T / k); continue
        if CFG.get("BORDES", "ejes") == "ejes":
            if not cons:
                d = nv
            elif len(cons) == 1:
                d = (nv - nv.dot(cons[0]) * cons[0])
            else:
                best = max(((a, b) for a in cons for b in cons if a is not b), key=lambda ab: ab[0].cross(ab[1]).length)
                d = best[0].cross(best[1]); d = d if d.dot(nv) > 0 else -d
        else:
            # todas las caras vecinas cuentan como limite: se elige la direccion que respete mas planos
            # manteniendose bien alineada con la normal (>= 0.5) para que el vertice entre en la pieza
            cands = [nv]
            for c in cons:
                q = nv - nv.dot(c) * c
                if q.length > 1e-6: cands.append(q.normalized())
            for i_ in range(len(cons)):
                for j_ in range(i_ + 1, len(cons)):
                    l_ = cons[i_].cross(cons[j_])
                    if l_.length > 0.2:
                        l_.normalize(); cands.append(l_ if l_.dot(nv) > 0 else -l_)
            def score(dd):
                return (sum(1 for c in cons if abs(dd.dot(c)) < 0.03), dd.dot(nv))
            ok = [dd for dd in cands if dd.dot(nv) >= 0.5]
            d = max(ok, key=score) if ok else nv
        if d.length < 1e-9: d = nv
        d.normalize(); k = max(d.dot(nv), 0.5); worst = min(worst, d.dot(nv))
        out[v] = d * (T / k)
    return out, worst

pads = {}; report["parche"] = {}
for side in (-1, 1):
    F = patch(side)
    off, worst = offsets(F)          # con las caras originales (las n-gonas dan normales fiables)
    # triangular el parche: soporte y almohadilla comparten exactamente los mismos triangulos (sin cruces)
    F = [f for f in bmesh.ops.triangulate(bm, faces=F, quad_method='FIXED', ngon_method='BEAUTY')['faces']]
    bm.normal_update()
    ys = [q.co.y for f in F for q in f.verts]
    report["parche"]["izq" if side < 0 else "der"] = {"caras": len(F), "y_mm": [round(min(ys) * 1000, 1), round(max(ys) * 1000, 1)],
                                                     "peor_alineacion": round(worst, 2)}
    pb = bmesh.new(); top, bot = {}, {}
    for v in off:
        top[v] = pb.verts.new(v.co.copy()); bot[v] = pb.verts.new(v.co - off[v])
    for f in F:
        pb.faces.new([top[q] for q in f.verts]); pb.faces.new([bot[q] for q in reversed(f.verts)])
    Fs = set(F)
    for f in F:                                    # costados: aristas del borde del parche
        lv = list(f.verts)
        for k in range(len(lv)):
            a, b = lv[k], lv[(k + 1) % len(lv)]
            e = bm.edges.get((a, b))
            if e and sum(1 for g in e.link_faces if g in Fs) == 1:
                pb.faces.new((top[b], top[a], bot[a], bot[b]))
    bmesh.ops.recalc_face_normals(pb, faces=pb.faces)
    name = PAD + ("Izq" if side < 0 else "Der")
    me = bpy.data.meshes.new(name); pb.to_mesh(me); pb.free(); me.materials.append(M_SIL)
    po = bpy.data.objects.new(name, me)
    for c in src.users_collection: c.objects.link(po)
    pads[side] = (po, off)

# ---------------------------------------------------------------- rebaje del soporte (toda la cara superior)
moved = 0
for side in (-1, 1):
    for v, d in pads[side][1].items():
        v.co -= d; moved += 1
bm.normal_update()
bm.transform(mw.inverted()); bm.to_mesh(dst.data); dst.data.update(); bm.free()
report["soporte"] = {"vertices_rebajados": moved}

# Donde la malla del soporte tiene cuerpos superpuestos (p. ej. la punta del girador), bajar la franja no basta:
# se resta ademas el volumen de cada almohadilla para que ninguna otra parte quede dentro de la silicona.
def _boolean(target, operand, op):
    m_ = target.modifiers.new("b_" + op.lower(), 'BOOLEAN'); m_.operation = op; m_.object = operand; m_.solver = 'EXACT'
    try: m_.use_hole_tolerant = True
    except Exception: pass
    bpy.context.view_layer.objects.active = target
    with bpy.context.temp_override(object=target, active_object=target):
        bpy.ops.object.modifier_apply(modifier=m_.name)
def integridad(o):
    b_ = bmesh.new(); b_.from_mesh(o.data)
    r_ = {"no_manifold": sum(1 for e in b_.edges if not e.is_manifold), "borde_abierto": sum(1 for e in b_.edges if e.is_boundary)}
    b_.free(); return r_
report["integridad"] = {"original": integridad(src), "tras_rebaje": integridad(dst)}

# ---------------------------------------------------------------- agujeros de los pivotes (booleano)
def band_bottom(tree, x, y, z_top):
    hit = tree.ray_cast(Vector((x, y, z_top - 0.0002)), Vector((0, 0, -1)))
    return hit[0].z if hit[0] else None
def tree_of(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
def pad_bottom_z(po, x, y):
    t = tree_of(po); h = t.ray_cast(Vector((x, y, 0.0)), Vector((0, 0, 1)))
    return h[0].z if h[0] else None

hb = bmesh.new()
for side in (-1, 1):
    for y in PEG_Y:
        x = side * (X_IN + X_OUT) / 2
        g = bmesh.ops.create_cone(hb, cap_ends=True, segments=24, radius1=HOLE_D / 2, radius2=HOLE_D / 2, depth=0.030)
        bmesh.ops.translate(hb, verts=g['verts'], vec=(x, y, 0.160))
hm = bpy.data.meshes.new("tmp_agujeros"); hb.to_mesh(hm); hb.free()
ho = bpy.data.objects.new("tmp_agujeros", hm); bpy.context.scene.collection.objects.link(ho)
# los cilindros no deben tocar la base: se limitan a la banda (bajo ella esta la ventana)
tsup = tree_of(dst)
lim = []
for side in (-1, 1):
    for y in PEG_Y:
        x = side * (X_IN + X_OUT) / 2
        top = tsup.ray_cast(Vector((x, y, 0.3)), Vector((0, 0, -1)))[0]
        bot = band_bottom(tsup, x, y, top.z)
        lim.append((x, y, top.z, bot))
        if bot is None or top.z - bot > 0.012: report["avisos"].append(f"pivote ({x:.4f},{y}): banda inesperada")
hb = bmesh.new()
for x, y, zt, zb in lim:
    g = bmesh.ops.create_cone(hb, cap_ends=True, segments=24, radius1=HOLE_D / 2, radius2=HOLE_D / 2, depth=(zt - zb) + 0.004)
    bmesh.ops.translate(hb, verts=g['verts'], vec=(x, y, (zt + zb) / 2))
hb.to_mesh(hm); hb.free(); hm.update()
mod = dst.modifiers.new("agujeros", 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = ho; mod.solver = 'EXACT'
try: mod.use_hole_tolerant = True
except Exception: pass
bpy.context.view_layer.objects.active = dst
with bpy.context.temp_override(object=dst, active_object=dst):
    bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.data.objects.remove(ho, do_unlink=True); bpy.data.meshes.remove(hm)
tsup = tree_of(dst); holes_ok = []
for x, y, zt, zb in lim:
    h = tsup.ray_cast(Vector((x, y, zt + 0.001)), Vector((0, 0, -1)))
    holes_ok.append(bool(h[0] is None or h[0].z < zb - 0.001))
report["agujeros_pasantes"] = holes_ok
report["integridad"]["tras_agujeros"] = integridad(dst)

# ---------------------------------------------------------------- pivotes de las almohadillas (union booleana)
pegs = []
for side in (() if "sin_pivotes" in argv else (-1, 1)):     # sin_pivotes: solo el cuerpo de la almohadilla
    po = pads[side][0]; pb = bmesh.new()
    for x, y, zt, zb in [l for l in lim if (l[0] > 0) == (side > 0)]:
        zp = pad_bottom_z(po, x, y)
        if zp is None: report["avisos"].append("sin fondo de almohadilla"); continue
        z_shaft_top = zp + 0.0006                     # se mete 0.6 mm en la almohadilla (union limpia)
        z_band_bot = zb
        z_shaft_bot = z_band_bot - 0.0002 - 0.0010     # entra 1 mm en la cabeza (sin caras coplanares)
        g = bmesh.ops.create_cone(pb, cap_ends=True, segments=24, radius1=PEG_D / 2, radius2=PEG_D / 2, depth=z_shaft_top - z_shaft_bot)
        bmesh.ops.translate(pb, verts=g['verts'], vec=(x, y, (z_shaft_top + z_shaft_bot) / 2))
        # cabeza conica: ancha arriba (traba bajo la banda), punta abajo para entrar; se orienta paralela a la
        # cara inferior de la banda, que esta inclinada (sigue el bisel del arco)
        pts = []
        for dx, dy in ((0.0024, 0), (0, 0.0024), (-0.0024, 0), (0, -0.0024)):      # alrededor del agujero
            org = Vector((x + dx, y + dy, zt + 0.003))
            h1 = tsup.ray_cast(org, Vector((0, 0, -1)))                             # cara superior (rebaje)
            h = tsup.ray_cast(h1[0] + Vector((0, 0, -0.0002)), Vector((0, 0, -1)))  # cara inferior de la banda
            pts.append(h[0])
        P0 = sum(pts, Vector()) / 4
        u = (pts[0] - pts[2]).cross(pts[1] - pts[3]).normalized()
        if u.z < 0: u = -u                                  # normal hacia arriba (hacia la banda)
        g = bmesh.ops.create_cone(pb, cap_ends=True, segments=24, radius1=0.0014, radius2=HEAD_D / 2, depth=HEAD_L)
        rot = Vector((0, 0, 1)).rotation_difference(u).to_matrix()
        bmesh.ops.rotate(pb, verts=g['verts'], cent=(0, 0, 0), matrix=rot)
        cen = P0 - u * (0.0002 + HEAD_L / 2)
        bmesh.ops.translate(pb, verts=g['verts'], vec=cen)
        pegs.append({"x": round(x, 4), "y": y, "vastago_mm": round((zp - z_band_bot) * 1000, 2), "inclinacion_cabeza_grados": round(math.degrees(u.angle(Vector((0, 0, 1)))), 1)})
    pm = bpy.data.meshes.new("tmp_pivotes"); pb.to_mesh(pm); pb.free()
    pobj = bpy.data.objects.new("tmp_pivotes", pm); bpy.context.scene.collection.objects.link(pobj)
    m2 = po.modifiers.new("pivotes", 'BOOLEAN'); m2.operation = 'UNION'; m2.object = pobj; m2.solver = 'EXACT'
    m2.use_self = True             # vastago y cabeza se solapan: sin esto quedan caras internas autointersectadas
    bpy.context.view_layer.objects.active = po
    with bpy.context.temp_override(object=po, active_object=po):
        bpy.ops.object.modifier_apply(modifier=m2.name)
    bpy.data.objects.remove(pobj, do_unlink=True); bpy.data.meshes.remove(pm)
report["pivotes"] = pegs

# ---------------------------------------------------------------- revision
def shrunk_tree(o, k=0.00005):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); b.normal_update()
    for v in b.verts: v.co -= v.normal * k
    t = BVHTree.FromBMesh(b); b.free(); return t
ts = tree_of(dst)
for side in (-1, 1):
    po = pads[side][0]
    b = bmesh.new(); b.from_mesh(po.data); b.transform(po.matrix_world)
    report[po.name] = {"manifold": all(e.is_manifold for e in b.edges), "volumen_mm3": round(b.calc_volume() * 1e9, 1),
                       "choca_con_soporte": bool(shrunk_tree(po).overlap(ts))}
    b.free()
# la cara superior de la almohadilla coincide con la superficie original
torig = tree_of(src); dev = 0.0
for side in (-1, 1):
    tp = tree_of(pads[side][0])
    for y in [Y0 + 0.0011 + (Y1 - Y0 - 0.0022) * k / 22 for k in range(23)]:
        for x in (side * (X_IN + 0.001), side * (X_IN + X_OUT) / 2, side * (X_OUT - 0.0008)):
            a = torig.ray_cast(Vector((x, y, 0.3)), Vector((0, 0, -1)))[0]; b_ = tp.ray_cast(Vector((x, y, 0.3)), Vector((0, 0, -1)))[0]
            if a and b_: dev = max(dev, abs(a.z - b_.z))
report["desviacion_superficie_mm"] = round(dev * 1000, 3)

# ---------------------------------------------------------------- STL para fabricar (mm)
outdir = os.path.join(os.path.dirname(bpy.data.filepath), "stl")
exported = []
if "save" in argv:                 # las pruebas sin guardar no tocan la carpeta stl/
    os.makedirs(outdir, exist_ok=True)
    for o in [dst] + [pads[s][0] for s in (-1, 1)]:
        bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
        fp = os.path.join(outdir, f"{bpy.path.display_name_from_filepath(bpy.data.filepath)}_{o.name}.stl")
        try:
            bpy.ops.wm.stl_export(filepath=fp, export_selected_objects=True, global_scale=1000.0, apply_modifiers=True)
            exported.append(os.path.basename(fp))
        except Exception as e:
            report["avisos"].append(f"STL {o.name}: {e}")
report["stl"] = exported if "save" in argv else "(solo al guardar)"
if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
