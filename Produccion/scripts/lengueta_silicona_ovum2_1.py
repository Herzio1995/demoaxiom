"""
Ovum2_1: la silicona del pesador y del girador se sujeta con una LENGUETA continua en vez de 4 tetones.

  - Regenera el cuerpo de cada almohadilla (3 mm) SIN tetones con silicona_pesador_ovum1_9.py (sin_pivotes) y lo
    traslada a la posicion actual de la pieza en la escena (en Ovum2_1 el conjunto esta mas abajo que el original).
  - Lengueta: a lo largo de la linea central de la almohadilla, por debajo. Trapecio: LG_RAIZ de ancho en la raiz,
    LG_PUNTA en la punta (se ensancha hacia abajo: queda trabada a presion), LG_PROF de profundidad.
  - Ranura en la cara superior del soporte de plastico: RA_ANCHO x RA_PROF, siguiendo la misma linea. Solo donde
    quedan al menos RA_MIN_PLASTICO mm de plastico bajo la ranura.
  - Los soportes del usuario NO se rehacen: solo se les resta la ranura (los agujeros de los tetones viejos quedan).
  - El molde se parte por la linea central, asi que la lengueta tambien queda partida a la mitad y se desmolda igual.

Uso en Blender abierto: exec(open(r"...\\lengueta_silicona_ovum2_1.py", encoding="utf-8").read())
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

O = bpy.data.objects; sc = bpy.context.scene
LG_RAIZ, LG_PUNTA, LG_PROF = 2.0, 2.5, 2.5          # lengueta (mm)
RA_ANCHO, RA_PROF = 2.2, 2.8                        # ranura en el plastico (mm)
RA_MIN_PLASTICO = 1.8                               # plastico minimo bajo la ranura (donde no alcanza, la ranura es menos profunda)
RA_PROF_MIN = 1.2                                   # profundidad minima de la ranura
RA_SALIDA = 4.0                                     # la ranura sigue 4 mm mas alla de cada extremo: sale abierta por las puntas
FIN_MARGEN = 0.3                                    # la lengueta corre todo el largo de la almohadilla
PASO = 0.5
PIEZAS = {"pesador": dict(SRC="PesadorPreSilicona", DST="PesadorSoporteSilicona", PAD="Silicona_Pesador_"),
          "girador": dict(SRC="SoporteGiradorPETG", DST="SoporteGiradorSilicona", PAD="Silicona_Girador_")}
rep = {"avisos": []}
_dir = os.path.join(os.path.dirname(bpy.data.filepath), "scripts")
if not os.path.isdir(_dir): _dir = r"G:\My Drive\TILINKA GENERAL\Tilinka Hardworks\Ovum Machine\scripts"

def tree(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
def bbox(o):
    ws = [o.matrix_world @ v.co for v in o.data.vertices]; return [Vector([min(w[k] for w in ws) for k in range(3)]), Vector([max(w[k] for w in ws) for k in range(3)])]
def link_tmp(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); return o
def drop(o):
    me = o.data; bpy.data.objects.remove(o, do_unlink=True)
    if me and me.users == 0: bpy.data.meshes.remove(me)
def boolean(target, operand, op, self_=False):
    m = target.modifiers.new("b", 'BOOLEAN'); m.operation = op; m.object = operand; m.solver = 'EXACT'; m.use_self = self_
    with bpy.context.temp_override(object=target, active_object=target): bpy.ops.object.modifier_apply(modifier=m.name)
def loft(secs):
    """solido a partir de secciones (listas de 4 puntos, mismo orden) a lo largo de la lengueta"""
    bm = bmesh.new(); vs = [[bm.verts.new(p) for p in s] for s in secs]
    bm.faces.new(list(reversed(vs[0]))); bm.faces.new(vs[-1])
    for a, b in zip(vs[:-1], vs[1:]):
        for k in range(4): bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); return bm

# ---------------------------------------------------------------- 1) cuerpos sin tetones, en la posicion actual
antes = {}
for PZ, C in PIEZAS.items():
    for lado in ("Izq", "Der"):
        o = O[C["PAD"] + lado]; antes[o.name] = (bbox(o), o.users_collection[0].name if o.users_collection else None)
for PZ, C in PIEZAS.items():
    usr = O[C["DST"]]
    # la almohadilla se genera sobre la pieza ORIGINAL (SRC); se lleva al soporte del usuario con la misma transformacion
    # que lleva SRC -> soporte del usuario (en Ovum2_1: pesador -43.4 en z; girador ademas -1.16 en y)
    A = usr.matrix_world @ O[C["SRC"]].matrix_world.inverted()
    usr.name = C["DST"] + "_usuario"; usr_data = usr.data.name
    argv0 = sys.argv; sys.argv = ["blender", "--", f"pieza={PZ}", "sin_pivotes"]
    try: exec(open(os.path.join(_dir, "silicona_pesador_ovum1_9.py"), encoding="utf-8").read(), {"__name__": "cuerpos"})
    finally: sys.argv = argv0
    drop(O[C["DST"]]); usr.name = C["DST"]; usr.data.name = usr_data; usr.hide_set(False)
    for lado in ("Izq", "Der"):
        o = O[C["PAD"] + lado]
        o.data.transform(o.matrix_world.inverted() @ A @ o.matrix_world)
        t_, q_, s_ = A.decompose()
        rep.setdefault("transformacion", {})[o.name] = {"traslado_mm": [round(c * 1000, 3) for c in t_], "escala": round(s_[0], 5)}

# ---------------------------------------------------------------- 2) lengueta y ranura
for PZ, C in PIEZAS.items():
    sup = O[C["DST"]]
    for lado in ("Izq", "Der"):
        pad = O[C["PAD"] + lado]; tp = tree(pad); ts = tree(sup)
        (p0, p1) = bbox(pad); xm = (p0.x + p1.x) / 2
        filas = []
        y = p0.y + FIN_MARGEN / 1000
        while y <= p1.y - FIN_MARGEN / 1000:
            h = tp.ray_cast(Vector((xm, y, p0.z - 0.01)), Vector((0, 0, 1)))[0]         # fondo de la almohadilla
            if h is not None:
                zs = h.z
                # plastico bajo la ranura: espesor del soporte medido al costado de la linea (los agujeros viejos estan en el centro)
                esp = []
                for dx in (-0.0026, 0.0026):
                    h1 = ts.ray_cast(Vector((xm + dx, y, zs + 0.0005)), Vector((0, 0, -1)))[0]
                    h2 = ts.ray_cast(h1 - Vector((0, 0, 1e-5)), Vector((0, 0, -1)))[0] if h1 else None
                    if h2: esp.append((h1.z - h2.z) * 1000)
                    elif h1: esp.append(99.0)                       # macizo hasta abajo
                e_ = min(esp) if esp else 99.0
                dp = max(RA_PROF_MIN, min(RA_PROF, e_ - RA_MIN_PLASTICO))   # profundidad de la ranura en este punto
                dp = max(0.3, min(dp, e_ - 0.8))                             # 0.8 mm de plastico debajo (en las puntas muy finas, marca de 0.3)
                filas.append((y, zs, e_, dp))
            y += PASO / 1000
        if len(filas) < 3: rep["avisos"].append(f"{pad.name}: no se encontro el fondo de la almohadilla"); continue
        tr = filas
        delgado = [f for f in tr if f[3] < RA_PROF - 1e-6]
        if delgado: rep["avisos"].append(f"{pad.name}: ranura menos profunda en {len(delgado)} puntos (min {min(f[3] for f in delgado):.1f} mm) por plastico delgado")
        m = lambda v: v / 1000.0
        # ranura (sobresale 1 mm hacia arriba para cortar limpio) y lengueta (entra 0.6 mm en la almohadilla)
        ext = [(tr[0][0] - m(RA_SALIDA),) + tr[0][1:]] + tr + [(tr[-1][0] + m(RA_SALIDA),) + tr[-1][1:]]   # sale por las puntas
        ran = [[Vector((xm + s * m(RA_ANCHO / 2), f[0], f[1] + z)) for s, z in ((-1, m(1.0)), (1, m(1.0)), (1, -m(f[3])), (-1, -m(f[3])))] for f in ext]
        # lengueta: 0.3 mm menos profunda que la ranura en cada punto; se ensancha de LG_RAIZ a LG_PUNTA hacia abajo
        def anch(f): return LG_RAIZ + (LG_PUNTA - LG_RAIZ) * max(0.0, min(1.0, (f[3] - 0.3) / LG_PROF))
        fin = [[Vector((xm + s * w, f[0], f[1] + z)) for s, w, z in ((-1, m(LG_RAIZ / 2), m(0.6)), (1, m(LG_RAIZ / 2), m(0.6)),
                                                                         (1, m(anch(f) / 2), -m(max(0.2, min(LG_PROF, f[3] - 0.3)))), (-1, m(anch(f) / 2), -m(max(0.2, min(LG_PROF, f[3] - 0.3)))))] for f in tr]
        r_ = link_tmp("tmp_ranura", loft(ran)); boolean(sup, r_, 'DIFFERENCE', True); drop(r_)
        f_ = link_tmp("tmp_lengueta", loft(fin)); boolean(pad, f_, 'UNION', True); drop(f_)
        b = bmesh.new(); b.from_mesh(pad.data); cerr = all(e.is_manifold for e in b.edges); vol = b.calc_volume(); b.free()
        rep[pad.name] = {"lengueta_largo_mm": round((tr[-1][0] - tr[0][0]) * 1000, 1), "largo_almohadilla_mm": round((p1.y - p0.y) * 1000, 1),
                         "ranura_y_mm": [round(ext[0][0] * 1000, 1), round(ext[-1][0] * 1000, 1)],
                         "plastico_min_bajo_ranura_mm": round(min(f[2] - f[3] for f in tr), 2), "prof_min_ranura_mm": round(min(f[3] for f in tr), 2), "cerrada": cerr,
                         "vol_cm3": round(vol * 1e6 * (pad.matrix_world.determinant()), 2)}
    b = bmesh.new(); b.from_mesh(sup.data); rep[sup.name] = {"aristas_abiertas": sum(1 for e in b.edges if not e.is_manifold)}; b.free()
print("RESULT " + json.dumps(rep))
result = rep
