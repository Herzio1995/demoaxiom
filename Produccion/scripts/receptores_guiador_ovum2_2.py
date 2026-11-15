# -*- coding: utf-8 -*-
"""
Corona receptora PETG entre el guiador (girador) y las bocas de las 5 bandejas PVC — Ovum2_2.

El guiador gira sobre un eje vertical en PIVOT y lanza el huevo radialmente hacia una bandeja.
Entre el barrido de las almohadillas (R ~37.6 mm) y el borde de los pisos (R 45-50 mm) hay un
hueco, y entre bocas vecinas (30, 70, 110, 150 grados) el huevo podria caer al bastidor.

La pieza es una herradura de 190 grados con:
  - 5 canaletas (una por bandeja) que bajan desde Z_IN hasta el piso de la bandeja,
  - lomos divisorios entre canaletas que desvian el huevo hacia la canaleta correcta,
  - una lengua que apoya SOBRE el piso PVC (borde final de 0.8 mm, el huevo baja, nunca sube),
  - un labio bajo el deck que topa contra el canto del piso (registro),
  - un agujero M3 avellanado por canaleta (o pegar con epoxi).
Las paredes PVC, cunas y zocalos se restan con holgura (DISPLACE_MM) y abiertos hacia arriba,
asi la pieza entra desde arriba con las bandejas montadas.

Ejecutar dentro de Blender (Ovum2_2*.blend):  exec(open(r"...\\receptores_guiador_ovum2_2.py").read())
Salida: coleccion PETG_Receptores_Guiador y stl/receptores_guiador/*.stl
"""
import bpy, bmesh, math, os
from mathutils import Vector
from mathutils.bvhtree import BVHTree

BASE = os.path.dirname(bpy.data.filepath)
OUT = os.path.join(BASE, "stl", "receptores_guiador")
COLL = "PETG_Receptores_Guiador"

PIVOT = Vector((0.0, -11.3))       # eje vertical del guiador (GiradorEje.001), mm
R_IN = 39.5                        # barrido max de las partes que giran a z>110 es 37.6
Z_IN = 124.8                       # altura del deck en R_IN (almohadillas terminan a z 128)
T_LENGUA = 2.0                     # espesor de la lengua sobre el PVC en el canto
T_PUNTA = 0.8                      # espesor de la punta de la lengua
LENGUA = 12.0                      # largo de la lengua sobre el piso
Z_BOT = 116.0                      # fondo plano del deck (lo que gira por debajo llega a z 110)
H_LOMO = 14.0                      # altura del lomo divisorio sobre la canaleta
TH0, TH1 = -14.0, 194.0            # extremos de la herradura (grados)
DTH = 1.0
N_RAMPA, N_LENGUA = 8, 8
DISPLACE_MM = 0.3                  # holgura contra PVC / PETG existente
M3_D, M3_CSK = 3.4, 6.6
ROT = {"SoporteGiradorSilicona", "Silicona_Girador_Izq", "Silicona_Girador_Der", "ShowGirador.002",
       "ShowGirador.003", "SoporteGuiadorCuadradoImprimir.001", "Pernos.001", "GiradorEje", "GiradorEje.001"}
TRAYS = ["RDown", "RTop", "Central", "LTop", "LDown"]   # en orden de angulo creciente
LIMITES = [TH0, 31.0, 70.0, 110.0, 149.0, TH1]           # lomos entre bandejas

sc = bpy.context.scene
vl = bpy.context.view_layer


def mm(v): return Vector((v[0] / 1000, v[1] / 1000, v[2] / 1000))


def polar(r, th):
    a = math.radians(th)
    return PIVOT.x + r * math.cos(a), PIVOT.y + r * math.sin(a)


# ---------------------------------------------------------------- muestreo de pisos
def floor_hit(obj, x, y):
    mi = obj.matrix_world.inverted()
    o = mi @ mm((x, y, 200)); d = (mi.to_3x3() @ Vector((0, 0, -1))).normalized()
    hit, loc, n, i = obj.ray_cast(o, d)
    if not hit: return None
    nz = (obj.matrix_world.to_3x3() @ n).normalized().z
    return (obj.matrix_world @ loc).z * 1000 if nz > 0.3 else None


pisos = {t: bpy.data.objects["PVC_Bandeja%s_Piso" % t] for t in TRAYS}


def tray_of(th):
    for k in range(5):
        if LIMITES[k] <= th <= LIMITES[k + 1]: return TRAYS[k], k
    return None, None


def lip(th):
    t, k = tray_of(th)
    if t is None: return None
    r = R_IN
    while r < 70:
        x, y = polar(r, th)
        z = floor_hit(pisos[t], x, y)
        if z is not None: return r, z
        r += 0.25
    return None


ths = [TH0 + i * DTH for i in range(int((TH1 - TH0) / DTH) + 1)]
lips = {th: lip(th) for th in ths}

# rango angular con piso de cada bandeja -> centro y semiancho de la canaleta
canal = {}
for k, t in enumerate(TRAYS):
    a = [th for th in ths if tray_of(th)[0] == t and lips[th] and lips[th][0] < 56]
    canal[t] = ((min(a) + max(a)) / 2, (max(a) - min(a)) / 2)


def interp_lip(th):
    """r y z del canto del piso; en los huecos sin piso interpola entre vecinos."""
    if lips[th] and lips[th][0] < 56: return lips[th]
    lo = [t for t in ths if t < th and lips[t] and lips[t][0] < 56]
    hi = [t for t in ths if t > th and lips[t] and lips[t][0] < 56]
    if not lo: return lips[hi[0]]
    if not hi: return lips[lo[-1]]
    a, b = lo[-1], hi[0]; f = (th - a) / (b - a)
    return (lips[a][0] * (1 - f) + lips[b][0] * f, lips[a][1] * (1 - f) + lips[b][1] * f)


def lomo(th):
    t, k = tray_of(th)
    c, w = canal[t]
    d = abs(th - c) - w
    if d <= 0: return 0.0
    lim = LIMITES[k + 1] if th > c else LIMITES[k]
    span = max(abs(lim - c) - w, 1.0)
    u = min(d / span, 1.0)
    return H_LOMO * math.sin(u * math.pi / 2) ** 1.5


# ---------------------------------------------------------------- heightfield -> solido
cols = []
for th in ths:
    rl, zl = interp_lip(th)
    has_floor = lips[th] is not None and lips[th][0] < 56
    h = lomo(th)
    t, _ = tray_of(th)
    z_lip_top = zl + T_LENGUA
    st = []
    for j in range(N_RAMPA + 1):                      # rampa R_IN -> canto
        r = R_IN + (rl - 0.5 - R_IN) * j / N_RAMPA    # 0.5 de holgura contra el canto del piso
        f = (r - R_IN) / max(rl - R_IN, 0.1)
        st.append((r, Z_IN + (z_lip_top - Z_IN) * f + h, Z_BOT))
    for j in range(N_LENGUA + 1):                     # lengua sobre el piso
        r = rl + LENGUA * j / N_LENGUA
        x, y = polar(r, th)
        zf = floor_hit(pisos[t], x, y) if has_floor else None
        u = j / N_LENGUA                              # espesor pleno hasta 60%, luego bisel
        tt = T_LENGUA if u <= 0.6 else T_LENGUA - (T_LENGUA - T_PUNTA) * (u - 0.6) / 0.4
        if zf is not None:                            # 0.3 sobre el PVC: no comparte cara con el piso
            st.append((r, zf + tt + h, zf + 0.3))
        else:                                         # hueco entre bandejas: lomo macizo
            st.append((r, zl + tt + h, Z_BOT))
    cols.append((th, st))

bm = bmesh.new()
grid_t, grid_b = [], []
for th, st in cols:
    rt, rb = [], []
    for r, zt, zb in st:
        x, y = polar(r, th)
        rt.append(bm.verts.new(mm((x, y, zt))))
        rb.append(bm.verts.new(mm((x, y, zb))))
    grid_t.append(rt); grid_b.append(rb)
ni, nj = len(grid_t), len(grid_t[0])
for i in range(ni - 1):
    for j in range(nj - 1):
        bm.faces.new((grid_t[i][j], grid_t[i][j + 1], grid_t[i + 1][j + 1], grid_t[i + 1][j]))
        bm.faces.new((grid_b[i][j], grid_b[i + 1][j], grid_b[i + 1][j + 1], grid_b[i][j + 1]))
for i in range(ni - 1):                               # canto interior y exterior
    bm.faces.new((grid_t[i][0], grid_t[i + 1][0], grid_b[i + 1][0], grid_b[i][0]))
    bm.faces.new((grid_t[i][-1], grid_b[i][-1], grid_b[i + 1][-1], grid_t[i + 1][-1]))
for i, sgn in ((0, 1), (ni - 1, -1)):                 # tapas en los extremos
    for j in range(nj - 1):
        q = (grid_t[i][j], grid_b[i][j], grid_b[i][j + 1], grid_t[i][j + 1])
        bm.faces.new(q if sgn > 0 else q[::-1])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

if COLL in bpy.data.collections:
    for o in list(bpy.data.collections[COLL].objects): bpy.data.objects.remove(o)
    coll = bpy.data.collections[COLL]
else:
    coll = bpy.data.collections.new(COLL); sc.collection.children.link(coll)
me = bpy.data.meshes.new("PETG_Receptor_Guiador"); bm.to_mesh(me); bm.free()
ring = bpy.data.objects.new("PETG_Receptor_Guiador", me); coll.objects.link(ring)
ring.color = (0.95, 0.45, 0.1, 1)


# ---------------------------------------------------------------- restas
def LOG(*a):
    print("[receptor]", *a, flush=True)


def boolean(obj, cutter, op='DIFFERENCE', solver='EXACT'):
    """EXACT para mallas PVC (pueden no ser cerradas); MANIFOLD para cortadores convexos cerrados
    (la EXACT con muchos prismas agoto 30 GB de memoria y cerro Blender)."""
    LOG("bool", cutter.name, solver, len(cutter.data.polygons), "caras")
    m = obj.modifiers.new("b", 'BOOLEAN'); m.object = cutter; m.operation = op
    m.solver = solver
    if solver == 'EXACT': m.use_self = True; m.use_hole_tolerant = True
    vl.objects.active = obj
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=m.name)
    bmc = bmesh.new(); bmc.from_mesh(obj.data)
    LOG("   -> aristas no manifold:", sum(1 for e in bmc.edges if not e.is_manifold)); bmc.free()


def cutter_from(src, dz_list, grow):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = src.evaluated_get(dg)
    bm = bmesh.new(); bm.from_mesh(ev.data); bm.transform(src.matrix_world)
    if grow:
        bm.normal_update()
        for v in bm.verts: v.co += v.normal * (grow / 1000)
    base = [v.co.copy() for v in bm.verts]
    out = bmesh.new()
    for dz in dz_list:
        tmp = bm.copy()
        for v in tmp.verts: v.co.z += dz / 1000
        me = bpy.data.meshes.new("tmp"); tmp.to_mesh(me); tmp.free()
        out.from_mesh(me); bpy.data.meshes.remove(me)
    bm.free()
    me = bpy.data.meshes.new("cut_" + src.name); out.to_mesh(me); out.free()
    c = bpy.data.objects.new("cut_" + src.name, me); sc.collection.objects.link(c)
    return c


def panel_cutters(src, grow, up=60.0, area_min=20.0):
    """Paredes plegadas -> un prisma convexo por panel plano (abierto hacia arriba `up` mm).
    Mas robusto que restar la malla original: la booleana exacta no deja aristas sueltas."""
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new(); bm.from_mesh(src.evaluated_get(dg).data); bm.transform(src.matrix_world)
    bm.faces.ensure_lookup_table(); bm.normal_update()
    grupos = []                                        # [normal, [faces]]
    for f in bm.faces:
        if f.calc_area() * 1e6 < area_min: continue
        n = f.normal.copy()
        for g in grupos:
            if abs(g[0].dot(n)) > 0.996:
                # mismo plano o el paralelo de enfrente (espesor del PVC)
                if abs((f.calc_center_median() - g[1][0].calc_center_median()).dot(g[0])) < 0.006:
                    g[1].append(f); break
        else:
            grupos.append([n, [f]])
    out = []
    for n, fs in grupos:
        pts = {v.co.copy().freeze() for f in fs for v in f.verts}
        nn = Vector((n.x, n.y, n.z)).normalized()
        hb = bmesh.new()
        g = grow / 1000                                # suma de Minkowski con un cubo: holgura en todas direcciones
        cubo = [Vector((sx * g, sy * g, sz * g)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        for p in pts:
            for d in cubo:
                q = Vector(p) + d
                hb.verts.new(q)
                if up: hb.verts.new(q + Vector((0, 0, up / 1000)))
        mn = [min(v.co[i] for v in hb.verts) for i in range(3)]
        mx = [max(v.co[i] for v in hb.verts) for i in range(3)]
        if any(mx[i] < RING_MN[i] or mn[i] > RING_MX[i] for i in range(3)):
            hb.free(); continue                        # este panel no toca la corona
        bmesh.ops.convex_hull(hb, input=hb.verts)
        loose = [v for v in hb.verts if not v.link_faces]
        bmesh.ops.delete(hb, geom=loose, context='VERTS')
        me = bpy.data.meshes.new("cutp"); hb.to_mesh(me); hb.free()
        c = bpy.data.objects.new("cutp_" + src.name, me); sc.collection.objects.link(c)
        out.append(c)
    bm.free()
    return out


def piso_cerrado(src, grow, voxel=0.12):
    """Piso PVC recortado a la zona de la corona y rehecho por voxeles: queda un solido cerrado
    (la malla original tiene aristas abiertas y la resta EXACTA abria la corona o colgaba Blender)."""
    c = cutter_from(src, [0.0], grow)
    bm = bmesh.new(); bm.from_mesh(c.data)
    m = 0.004
    for ax in range(3):
        for sgn, val in ((1, RING_MN[ax] - m), (-1, RING_MX[ax] + m)):
            no = Vector((0, 0, 0)); no[ax] = -sgn
            co = Vector((0, 0, 0)); co[ax] = val
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True)
    bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=0)
    bm.to_mesh(c.data); bm.free()
    c.data.remesh_voxel_size = voxel / 1000; c.data.remesh_voxel_adaptivity = 0.0
    vl.objects.active = c
    with bpy.context.temp_override(object=c, active_object=c):
        bpy.ops.object.voxel_remesh()
    return c


_rw = [ring.matrix_world @ v.co for v in ring.data.vertices]
RING_MN = [min(v[i] for v in _rw) for i in range(3)]
RING_MX = [max(v[i] for v in _rw) for i in range(3)]

cut_src = []
for o in sc.objects:
    if o.type != 'MESH' or not o.visible_get(): continue
    if o.name.startswith(("PVC_Bandeja", "PETG_Cuna", "PETG_Zocalo", "PETG_Separador")):
        cut_src.append(o)
cerca = []
for o in cut_src:
    ws = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = [min(v[i] for v in ws) for i in range(3)]; mx = [max(v[i] for v in ws) for i in range(3)]
    if not any(mx[i] < RING_MN[i] - 0.001 or mn[i] > RING_MX[i] + 0.001 for i in range(3)):
        cerca.append(o)
for o in cerca:
    if o.name.endswith("_Piso"):
        # la lengua ya va 0.15 mm sobre el piso; esta resta solo limpia los cantos oblicuos.
        # Si abriera la malla se deshace (la rampa termina igual 0.25 mm antes del canto).
        for holg in (0.2,):
            respaldo = ring.data.copy()
            c = piso_cerrado(o, holg)
            boolean(ring, c, solver='MANIFOLD'); bpy.data.objects.remove(c)
            bmc = bmesh.new(); bmc.from_mesh(ring.data)
            abiertas = sum(1 for e in bmc.edges if not e.is_manifold); bmc.free()
            if not abiertas:
                bpy.data.meshes.remove(respaldo); LOG("   piso", o.name, "restado con holgura", holg); break
            viejo = ring.data; ring.data = respaldo; bpy.data.meshes.remove(viejo)
        else:
            LOG("   resta de", o.name, "deshecha")
    else:
        for c in panel_cutters(o, DISPLACE_MM, area_min=1.0):
            boolean(ring, c, solver='MANIFOLD'); bpy.data.objects.remove(c)

# agujeros M3 avellanados, uno por canaleta, en la lengua
agujeros = []
for t in TRAYS:
    c, w = canal[t]
    rl, zl = interp_lip(round(c))
    x, y = polar(rl + LENGUA * 0.35, c)
    zf = floor_hit(pisos[t], x, y) or zl
    z_top = zf + T_LENGUA
    dcs = (M3_CSK - M3_D) / 2 + 0.3
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=M3_D / 2000, depth=0.06, location=(x / 1000, y / 1000, 0.12))
    h1 = bpy.context.active_object
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=M3_D / 2000, radius2=(M3_CSK / 2 + 0.3) / 1000, depth=dcs / 1000,
                                    location=(x / 1000, y / 1000, (z_top + 0.3 - dcs / 2) / 1000))
    h2 = bpy.context.active_object
    boolean(ring, h1, solver='MANIFOLD'); boolean(ring, h2, solver='MANIFOLD')
    bpy.data.objects.remove(h1); bpy.data.objects.remove(h2)
    agujeros.append((t, round(x, 1), round(y, 1)))

# ---------------------------------------------------------------- verificacion
bm = bmesh.new(); bm.from_mesh(ring.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
no_manifold = sum(1 for e in bm.edges if not e.is_manifold)
volumen_cm3 = bm.calc_volume() * 1e6
bm.to_mesh(ring.data); bm.free(); ring.data.update()
dg = bpy.context.evaluated_depsgraph_get()
rv = [ring.matrix_world @ v.co * 1000 for v in ring.data.vertices]
# 1) envolvente de barrido de lo que gira: Rmax(z)
env = {}
for n in ROT:
    o = bpy.data.objects.get(n)
    if not o: continue
    for v in o.data.vertices:
        w = o.matrix_world @ v.co * 1000
        zk = int(w.z)
        env[zk] = max(env.get(zk, 0), math.hypot(w.x - PIVOT.x, w.y - PIVOT.y))
min_gap = 1e9
for v in rv:
    r = math.hypot(v.x - PIVOT.x, v.y - PIVOT.y)
    for zk in (int(v.z) - 1, int(v.z), int(v.z) + 1):
        if zk in env: min_gap = min(min_gap, r - env[zk])


# 2) choques con todo lo estatico visible
def bvh(o):
    ev = o.evaluated_get(dg); bm = bmesh.new(); bm.from_mesh(ev.data); bm.transform(o.matrix_world)
    t = BVHTree.FromBMesh(bm); bm.free(); return t


rb = bvh(ring)
choques = []
for o in sc.objects:
    if o.type != 'MESH' or not o.visible_get() or o == ring or o.name in ROT or o.name.startswith("Huevo"): continue
    ws = [o.matrix_world @ Vector(c) * 1000 for c in o.bound_box]
    if max(v.z for v in ws) < 105 or min(v.z for v in ws) > 145: continue
    tb = bvh(o)
    dmin, dentro = 1e9, 0                              # distancia minima (mm) y vertices dentro del solido
    for v in ring.data.vertices:
        w = ring.matrix_world @ v.co
        loc, nrm, i, d = tb.find_nearest(w, 0.004)
        if loc is None: continue
        dmin = min(dmin, d * 1000)
        n_hits, p = 0, w.copy()                        # paridad de rayo en +x
        for _ in range(20):
            hl, hn, hi, hd = tb.ray_cast(p, Vector((1, 0.0137, 0.0071)))
            if hl is None: break
            n_hits += 1; p = hl + Vector((1, 0.0137, 0.0071)).normalized() * 1e-6
        if n_hits % 2 == 1: dentro += 1
    if dmin < 1e8: choques.append((o.name, round(dmin, 2), dentro, bool(rb.overlap(tb))))

# 3) bajo cada agujero: espacio libre para la tuerca (8 mm bajo el piso)
libre = []
for t, x, y in agujeros:
    zf = floor_hit(pisos[t], x, y)
    hit, loc, n, i, ob, m = sc.ray_cast(dg, mm((x, y, (zf or 120) - 2.5)), Vector((0, 0, -1)))
    libre.append((t, round((zf or 0) - 2 - loc.z * 1000, 1) if hit else 999, ob.name if hit else None))

os.makedirs(OUT, exist_ok=True)
for o in sc.objects: o.select_set(False)
ring.select_set(True); vl.objects.active = ring
path = os.path.join(OUT, "Receptor_Guiador_PETG.stl")
bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1000.0, apply_modifiers=True)
dims = [round(d * 1000, 1) for d in ring.dimensions]

with open(os.path.join(OUT, "Receptor_Guiador_lista.txt"), "w", encoding="utf-8") as f:
    f.write("Corona receptora del guiador (PETG) - generado por scripts/receptores_guiador_ovum2_2.py\n")
    f.write("Medidas (mm): %s x %s x %s\n" % tuple(dims))
    f.write("Canaletas (centro, semiancho en grados):\n")
    for t in TRAYS: f.write("  %-8s %.1f  +-%.1f\n" % (t, canal[t][0], canal[t][1]))
    f.write("Agujeros M3 avellanados (taladrar D3.4 en el piso PVC en esta posicion x,y):\n")
    for t, x, y in agujeros: f.write("  %-8s x=%.1f y=%.1f\n" % (t, x, y))
    f.write("Holgura minima con lo que gira: %.1f mm\n" % min_gap)

result = {"dims": dims, "no_manifold": no_manifold, "vol_cm3": round(volumen_cm3, 1), "canal": {t: [round(a, 1) for a in canal[t]] for t in TRAYS}, "min_gap_giro": round(min_gap, 2),
          "choques": choques, "bajo_agujeros": libre, "agujeros": agujeros, "stl": path}
