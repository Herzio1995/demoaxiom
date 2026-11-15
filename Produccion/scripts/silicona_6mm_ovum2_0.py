"""
Ovum2_0: almohadillas de silicona de 6 mm (antes 3 mm), con geometria simplificada.

Que hace (para pesador y girador)
  - Parte de los soportes TAL COMO ESTAN en la escena (PesadorSoporteSilicona / SoporteGiradorSilicona), que el
    usuario engroso ~3 mm por debajo de la banda. No los rehace desde la pieza original.
  - Rebaja de nuevo, ahora T = 6 mm: se corta todo lo que queda sobre la nueva cara inferior (incluye el rebaje viejo).
    Donde la banda de plastico no da para 6 mm se deja siempre MIN_PLA de plastico bajo la silicona.
  - Almohadilla simplificada: su cara superior es la superficie original (el huevo no cambia de altura) y la
    inferior es la misma superficie bajada en VERTICAL. Lados y extremos quedan como paredes verticales planas:
    desaparecen los labios delgados de los extremos.
  - Pivotes: vastago de 3.4 mm y cabeza conica de 5.4 mm bajo la banda (sin cambios de tamano).

Uso en Blender abierto:  exec(open(r"...\\silicona_6mm_ovum2_0.py", encoding="utf-8").read())
Uso en segundo plano:    blender --background Ovum2_0.blend --python silicona_6mm_ovum2_0.py [-- save]
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects
T = 0.0060                          # espesor de la silicona (vertical en zonas planas)
K_MIN = 0.5                         # en rampas la bajada vertical crece hasta T/0.5 para mantener espesor
MIN_PLA = 0.0025                    # plastico minimo bajo la silicona (vertical)
HOLGURA_LADO = 0.0003               # el corte sobresale de los lados (evita caras coincidentes)
PEG_D = 0.0034
HOLE_D = 0.0035                     # 0.1 mm mas que el pivote: no coincide con los agujeros que ya traia el soporte
HEAD_D, HEAD_L, HEAD_TIP = 0.0054, 0.0026, 0.0014
EPS = 2e-4
PIEZAS = {
    "pesador": dict(SRC="PesadorPreSilicona", DST="PesadorSoporteSilicona", PAD="Silicona_Pesador_",
                    X_IN=0.0150, X_OUT=0.0278, Y0=-0.0995, Y1=-0.0425, PEG_Y=(-0.0850, -0.0660)),
    "girador": dict(SRC="SoporteGiradorPETG", DST="SoporteGiradorSilicona", PAD="Silicona_Girador_",
                    X_IN=0.0150, X_OUT=0.0253, Y0=-0.0430, Y1=0.0180, PEG_Y=(-0.0220, -0.0030)),
}
report = {"avisos": []}

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
    try: m.use_hole_tolerant = True
    except Exception: pass
    with bpy.context.temp_override(object=target, active_object=target):
        bpy.ops.object.modifier_apply(modifier=m.name)
def integridad(o):
    b = bmesh.new(); b.from_mesh(o.data); r = sum(1 for e in b.edges if not e.is_manifold); b.free(); return r
def volumen(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); v = b.calc_volume(); b.free(); return round(v * 1e6, 2)

for PZ, C in PIEZAS.items():
    src, dst = O[C["SRC"]], O[C["DST"]]
    rep = report[PZ] = {"no_manifold_soporte_antes": integridad(dst), "vol_soporte_antes_cm3": volumen(dst)}
    # ------------------------------------------------ 2) cara superior original de cada pared
    bm = bmesh.new(); bm.from_mesh(src.data); bm.transform(src.matrix_world); bm.normal_update()
    tsup0 = tree_of(dst); pads = {}; drops = []
    def disponible(v):
        """espesor vertical de plastico bajo el punto v de la superficie original (hasta la cara inferior de la banda)"""
        h1 = tsup0.ray_cast(Vector((v.co.x * 0.999, v.co.y, 0.3)), Vector((0, 0, -1)))[0]      # techo actual del soporte
        if h1 is None or v.co.z - h1.z > 0.005: return None
        h2 = tsup0.ray_cast(h1 - Vector((0, 0, 1e-5)), Vector((0, 0, -1)))[0]
        return (v.co.z - h2.z) if h2 else None
    for side in (-1, 1):
        F = [f for f in bm.faces if f.normal.z > 0.4 and all(q.co.z > 0.155 and C["X_IN"] - EPS <= side * q.co.x <= C["X_OUT"] + EPS
             and C["Y0"] <= q.co.y <= C["Y1"] for q in f.verts)]
        Fs = set(F); drop_ = {}; nrm = {}
        xs_ = [abs(q.co.x) for f in F for q in f.verts]; xa, xb = min(xs_), max(xs_)
        for v in {q for f in F for q in f.verts}:
            nrm[v] = sum((f.normal for f in v.link_faces if f in Fs), Vector()).normalized(); nz = nrm[v].z
            d = T / max(nz, K_MIN); av = disponible(v)
            if av is not None: d = min(d, av - MIN_PLA)
            drop_[v] = d; drops.append(d)
        F = bmesh.ops.triangulate(bm, faces=F, quad_method='FIXED', ngon_method='BEAUTY')['faces']
        Fs = set(F)
        # direccion hacia afuera (en planta) de cada vertice del borde del parche
        afuera = {}
        for f in F:
            c = f.calc_center_median()
            for e in f.edges:
                if sum(1 for g in e.link_faces if g in Fs) != 1: continue
                a_, b_ = e.verts; t_ = (b_.co - a_.co); n2 = Vector((t_.y, -t_.x, 0))
                if n2.length < 1e-9: continue
                n2.normalize()
                if n2.dot(Vector((c.x - a_.co.x, c.y - a_.co.y, 0))) > 0: n2 = -n2
                for q in (a_, b_): afuera[q] = afuera.get(q, Vector()) + n2
        def prism(z_top_fn, lado=0.0):
            pb = bmesh.new(); top, bot = {}, {}
            for v in drop_:
                # el cortador sobresale del borde hacia afuera, siguiendo la inclinacion de la cara
                ex = Vector((0, 0, 0))
                if lado and v in afuera and afuera[v].length > 1e-6:
                    ex = afuera[v].normalized() * lado
                    # altura: el plano MAS BAJO de los triangulos inferiores vecinos, prolongado hasta el punto desplazado
                    zs_ = []
                    for f in v.link_faces:
                        if f not in Fs: continue
                        P_ = [q.co - Vector((0, 0, drop_[q])) for q in f.verts]
                        n_ = (P_[1] - P_[0]).cross(P_[2] - P_[0])
                        if abs(n_.z) > 1e-12: zs_.append(-(n_.x * ex.x + n_.y * ex.y) / n_.z)
                    ex.z = max(-5e-4, min(3e-4, min(zs_))) if zs_ else 0.0
                if lado: ex.z -= 1e-4         # el corte baja 0.1 mm mas que la almohadilla: nunca queda plastico dentro
                top[v] = pb.verts.new(z_top_fn(v) + ex); bot[v] = pb.verts.new(v.co - Vector((0, 0, drop_[v])) + ex)
            for f in F:
                pb.faces.new([top[q] for q in f.verts]); pb.faces.new([bot[q] for q in reversed(f.verts)])
            for f in F:
                lv = list(f.verts)
                for k in range(len(lv)):
                    a, b = lv[k], lv[(k + 1) % len(lv)]
                    e = bm.edges.get((a, b))
                    if e and sum(1 for g in e.link_faces if g in Fs) == 1:
                        pb.faces.new((top[b], top[a], bot[a], bot[b]))
            bmesh.ops.recalc_face_normals(pb, faces=pb.faces); return pb
        pads[side] = (prism(lambda v: v.co.copy()),                          # almohadilla
                      prism(lambda v: Vector((v.co.x, v.co.y, 0.25)), HOLGURA_LADO))       # cortador (todo lo que este encima)
    bm.free(); rep["bajada_vertical_mm"] = [round(min(drops) * 1000, 2), round(max(drops) * 1000, 2)]
    # ------------------------------------------------ 3) rebajar el soporte y crear las almohadillas
    for side in (-1, 1):
        _b = pads[side][1]; _b.faces.ensure_lookup_table(); _t = BVHTree.FromBMesh(_b)
        rep.setdefault("cortador", []).append({"abiertas": sum(1 for e in _b.edges if not e.is_manifold),
            "autocruces": sum(1 for i_, j_ in _t.overlap(_t) if i_ < j_ and not (set(_b.faces[i_].verts) & set(_b.faces[j_].verts)))})
        cut = link_tmp("tmp_cortador", pads[side][1]); boolean(dst, cut, 'DIFFERENCE', self_=True); drop(cut)   # use_self: el soporte tiene cuerpos superpuestos
    for side in (-1, 1):
        name = C["PAD"] + ("Izq" if side < 0 else "Der"); old = O[name]
        mats = list(old.data.materials); old_me = old.data
        me = bpy.data.meshes.new(name); pads[side][0].to_mesh(me); pads[side][0].free()
        for m in mats: me.materials.append(m)
        old.data = me; old.matrix_world = old.matrix_world.__class__.Identity(4)
        bpy.data.meshes.remove(old_me); old_me = None
    # ------------------------------------------------ 4) agujeros de los pivotes en la banda
    tsup = tree_of(dst); lim = []
    for side in (-1, 1):
        for y in C["PEG_Y"]:
            x = side * (C["X_IN"] + C["X_OUT"]) / 2
            tp = tree_of(O[C["PAD"] + ("Izq" if side < 0 else "Der")])
            zp = tp.ray_cast(Vector((x, y, 0.0)), Vector((0, 0, 1)))[0].z            # fondo de la almohadilla
            # cara inferior de la banda, medida junto al agujero (el soporte ya trae los agujeros de antes)
            zbs = []
            for dx in (-0.0026, 0.0026):
                h1 = tsup.ray_cast(Vector((x + dx, y, zp + 0.003)), Vector((0, 0, -1)))[0]
                h2 = tsup.ray_cast(h1 - Vector((0, 0, 1e-5)), Vector((0, 0, -1)))[0] if h1 else None
                if h2: zbs.append(h2.z)
            zb = sum(zbs) / len(zbs) if zbs else None
            if zb is None or zp - zb > 0.012: rep.setdefault("avisos", []).append(f"banda inesperada en y={y}")
            lim.append((side, x, y, zp, zb))
    hb = bmesh.new()
    for side, x, y, zp, zb in lim:
        g = bmesh.ops.create_cone(hb, cap_ends=True, segments=24, radius1=HOLE_D / 2, radius2=HOLE_D / 2, depth=(zp - zb) + 0.003)
        bmesh.ops.translate(hb, verts=g['verts'], vec=(x, y, (zp + zb) / 2))
    ho = link_tmp("tmp_agujeros", hb); boolean(dst, ho, 'DIFFERENCE'); drop(ho)
    tsup = tree_of(dst)
    rep["agujeros_pasantes"] = [tsup.ray_cast(Vector((x, y, zp - 0.0001)), Vector((0, 0, -1)))[0] is None
                                or tsup.ray_cast(Vector((x, y, zp - 0.0001)), Vector((0, 0, -1)))[0].z < zb - 0.001 for _, x, y, zp, zb in lim]
    rep["plastico_bajo_silicona_mm"] = [round((zp - zb) * 1000, 2) for _, x, y, zp, zb in lim]
    # ------------------------------------------------ 5) pivotes (vastago + cabeza paralela a la banda)
    for side in (-1, 1):
        po = O[C["PAD"] + ("Izq" if side < 0 else "Der")]; pb = bmesh.new()
        for s_, x, y, zp, zb in lim:
            if s_ != side: continue
            z_top = zp + 0.0008; z_bot = zb - 0.0012
            g = bmesh.ops.create_cone(pb, cap_ends=True, segments=24, radius1=PEG_D / 2, radius2=PEG_D / 2, depth=z_top - z_bot)
            bmesh.ops.translate(pb, verts=g['verts'], vec=(x, y, (z_top + z_bot) / 2))
            pts = []
            for dx, dy in ((0.0024, 0), (0, 0.0024), (-0.0024, 0), (0, -0.0024)):
                # desde arriba: 1er contacto = cara superior de la banda (ya rebajada), 2o = cara inferior
                h1 = tsup.ray_cast(Vector((x + dx, y + dy, 0.3)), Vector((0, 0, -1)))[0]
                h2 = tsup.ray_cast(h1 - Vector((0, 0, 1e-5)), Vector((0, 0, -1)))[0] if h1 else None
                pts.append(h2 if h2 and abs(h2.z - zb) < 0.003 else Vector((x + dx, y + dy, zb)))
            P0 = sum(pts, Vector()) / 4
            u = (pts[0] - pts[2]).cross(pts[1] - pts[3]).normalized()
            if u.z < 0: u = -u
            g = bmesh.ops.create_cone(pb, cap_ends=True, segments=24, radius1=HEAD_TIP, radius2=HEAD_D / 2, depth=HEAD_L)
            bmesh.ops.rotate(pb, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(u).to_matrix())
            bmesh.ops.translate(pb, verts=g['verts'], vec=P0 - u * (0.0002 + HEAD_L / 2))
        pg = link_tmp("tmp_pivotes", pb); boolean(po, pg, 'UNION', self_=True); drop(pg)
    # ------------------------------------------------ revision
    ts = tree_of(dst)
    for side in ("Izq", "Der"):
        po = O[C["PAD"] + side]
        b = bmesh.new(); b.from_mesh(po.data); b.transform(po.matrix_world); b.normal_update()
        for v in b.verts: v.co -= v.normal * 0.00005
        t = BVHTree.FromBMesh(b)
        rep[po.name] = {"manifold": all(e.is_manifold for e in b.edges), "vol_cm3": volumen(po), "caras": len(po.data.polygons),
                        "choca_con_soporte": bool(t.overlap(ts))}
        b.free()
    rep["no_manifold_soporte_despues"] = integridad(dst); rep["vol_soporte_despues_cm3"] = volumen(dst)

if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
result = report
