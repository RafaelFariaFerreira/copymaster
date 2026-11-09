#!/usr/bin/env python3
"""Gera as ilustrações do README (capa e diagramas) em SVG, com as fontes embutidas.

Uso (a partir da raiz do repositório):
    pip install fonttools brotli
    python3 docs/gerar_imagens.py

As fontes (Fraunces, Inter, Caveat e JetBrains Mono, todas sob a SIL Open Font
License) são baixadas do repositório google/fonts na primeira execução e ficam em
docs/.fontes/, fora do Git. Cada SVG leva só os caracteres que usa, em WOFF2, para
ficar igual em qualquer navegador sem depender das fontes instaladas.
"""
import base64
import io
import os
import urllib.request
from collections import defaultdict
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.fontes')
GF = 'https://github.com/google/fonts/raw/main/ofl/'
SOURCES = {
    'Fraunces': 'fraunces/Fraunces%5BSOFT,WONK,opsz,wght%5D.ttf',
    'Inter': 'inter/Inter%5Bopsz,wght%5D.ttf',
    'Caveat': 'caveat/Caveat%5Bwght%5D.ttf',
    'JetBrainsMono': 'jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf',
}
# estilo: (fonte, eixos, família no CSS, peso no CSS, pilha de reserva)
STYLES = {
    'serif': ('Fraunces', {'opsz': 72, 'wght': 600, 'SOFT': 50, 'WONK': 0}, 'CM Serif', 600, "Georgia,'Times New Roman',serif"),
    'sans': ('Inter', {'opsz': 14, 'wght': 400}, 'CM Sans', 400, "'Segoe UI',Helvetica,Arial,sans-serif"),
    'sans6': ('Inter', {'opsz': 14, 'wght': 600}, 'CM Sans', 600, "'Segoe UI',Helvetica,Arial,sans-serif"),
    'sans7': ('Inter', {'opsz': 14, 'wght': 700}, 'CM Sans', 700, "'Segoe UI',Helvetica,Arial,sans-serif"),
    'hand': ('Caveat', {'wght': 600}, 'CM Hand', 600, "'Comic Sans MS',cursive"),
    'mono': ('JetBrainsMono', {'wght': 500}, 'CM Mono', 500, 'Menlo,Consolas,monospace'),
}

PAPER = '#FBF6EC'
PAPER2 = '#F4ECDD'
CARD = '#FFFFFF'
LINE = '#E6DCCB'
INK = '#1F1B16'
INK2 = '#4D453B'
MUTED = '#857B6C'
RED = '#D2402A'
RED_D = '#A8321F'
RED_T = '#FCE6DF'
BLUE = '#2F5D8A'
BLUE_T = '#E3ECF5'
YELLOW = '#FFE27A'
WHITE = '#FFFFFF'


# ---------------------------------------------------------------- fontes

class Font:
    def __init__(self, key):
        src, axes, self.family, self.weight, self.fallback = STYLES[key]
        os.makedirs(CACHE, exist_ok=True)
        var = os.path.join(CACHE, src + '.ttf')
        if not os.path.exists(var):
            print('baixando', src)
            urllib.request.urlretrieve(GF + SOURCES[src], var)
        static = os.path.join(CACHE, f'{key}.ttf')
        if not os.path.exists(static):
            inst = instancer.instantiateVariableFont(TTFont(var), axes)
            inst.save(static)
        self.path = static
        self.tt = TTFont(static)
        self.cmap = self.tt.getBestCmap()
        self.hmtx = self.tt['hmtx']
        self.upm = self.tt['head'].unitsPerEm

    def width(self, text, size, ls=0):
        w = 0
        for ch in text:
            g = self.cmap.get(ord(ch))
            if g is None:
                raise SystemExit(f'caractere sem glifo em {self.family}: {ch!r} ({text!r})')
            w += self.hmtx[g][0]
        return w * size / self.upm + ls * max(len(text) - 1, 0)

    def woff2(self, chars):
        font = TTFont(self.path)
        opts = subset.Options()
        opts.layout_features = ['kern', 'liga', 'calt', 'ccmp', 'locl', 'mark', 'mkmk']
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(text=''.join(sorted(set(chars) | {' '})))
        sub.subset(font)
        font.flavor = 'woff2'
        buf = io.BytesIO()
        font.save(buf)
        return base64.b64encode(buf.getvalue()).decode()


FONTS = {k: Font(k) for k in STYLES}


def wrap(text, f, size, maxw):
    lines = []
    for para in text.split('\n'):
        cur = ''
        for word in para.split(' '):
            trial = (cur + ' ' + word).strip()
            if cur and FONTS[f].width(trial, size) > maxw:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return lines


def fit(text, f, maxw, start):
    size = start
    while FONTS[f].width(text, size) > maxw:
        size -= 0.5
    return size


# ---------------------------------------------------------------- tela

class Canvas:
    def __init__(self, w, h, title, desc, rx=24):
        self.w, self.h, self.title, self.desc, self.rx = w, h, title, desc, rx
        self.parts, self.defs = [], []
        self.used = defaultdict(set)

    def add(self, *xs):
        self.parts.extend(xs)

    def text(self, x, y, t, f='sans', size=16, fill=INK, anchor='start', ls=0, op=None):
        self.used[f].update(t)
        a = f' text-anchor="{anchor}"' if anchor != 'start' else ''
        l = f' letter-spacing="{ls}"' if ls else ''
        o = f' opacity="{op}"' if op is not None else ''
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" class="{f}" font-size="{size}" fill="{fill}"{a}{l}{o}>{escape(t)}</text>')
        return FONTS[f].width(t, size, ls)

    def para(self, x, y, t, f, size, maxw, lh, fill=INK2, anchor='start'):
        """Texto quebrado em linhas; devolve a linha de base da última linha."""
        lines = wrap(t, f, size, maxw)
        for i, ln in enumerate(lines):
            self.text(x, y + i * lh, ln, f, size, fill, anchor)
        return y + (len(lines) - 1) * lh

    def svg(self):
        css = []
        for key, chars in sorted(self.used.items()):
            fnt = FONTS[key]
            css.append(f"@font-face{{font-family:'{fnt.family}';font-weight:{fnt.weight};"
                       f"src:url(data:font/woff2;base64,{fnt.woff2(chars)}) format('woff2')}}")
        for key in self.used:
            fnt = FONTS[key]
            css.append(f".{key}{{font-family:'{fnt.family}',{fnt.fallback};font-weight:{fnt.weight}}}")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">'
                f'<title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>'
                f'<defs><style>{"".join(css)}</style>'
                f'<clipPath id="clip"><rect width="{self.w}" height="{self.h}" rx="{self.rx}"/></clipPath>'
                f'<marker id="ah" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                f'<path d="M0 0 L10 5 L0 10 z" fill="{INK2}"/></marker>'
                f'{"".join(self.defs)}</defs>'
                f'<g clip-path="url(#clip)"><rect width="{self.w}" height="{self.h}" fill="{PAPER}"/>'
                f'{"".join(self.parts)}</g></svg>')

    def save(self, name):
        path = os.path.join(HERE, name)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(self.svg())
        print(f'{name}: {self.w}x{self.h}, {os.path.getsize(path) // 1024} KB')


def rect(c, x, y, w, h, fill=CARD, stroke=LINE, rx=14, sw=1.5, dash=None, op=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    o = f' opacity="{op}"' if op is not None else ''
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ''
    c.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"{s}{d}{o}/>')


def arrow(c, d, color=INK2, sw=1.8, dash=None):
    ds = f' stroke-dasharray="{dash}"' if dash else ''
    c.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
          f'stroke-linejoin="round" marker-end="url(#ah)"{ds}/>')


def check(c, x, y, s=1, color=RED, sw=3):
    c.add(f'<path d="M{x} {y} l{6*s} {7*s} l{13*s} {-15*s}" fill="none" stroke="{color}" stroke-width="{sw}" '
          f'stroke-linecap="round" stroke-linejoin="round"/>')


def icon(kind, x, y, size=18, color=INK, sw=1.7):
    """Ícones de 20x20, desenhados com traço."""
    st = f'fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
    body = {
        'lp': f'<rect x="2" y="3" width="16" height="14" rx="2" {st}/><path d="M2 7h16" {st}/>'
              f'<rect x="6" y="11" width="8" height="3" rx="1.5" fill="{color}"/>',
        'site': f'<circle cx="10" cy="10" r="7.5" {st}/><ellipse cx="10" cy="10" rx="3.3" ry="7.5" {st}/>'
                f'<path d="M2.5 10h15" {st}/>',
        'email': f'<rect x="2" y="4.5" width="16" height="11" rx="1.5" {st}/><path d="M2.6 5.4 10 11l7.4-5.6" {st}/>',
        'prosp': f'<path d="M2.5 9.2 17.5 3l-5 14-3-6.2z" {st}/><path d="M9.5 10.8 17.5 3" {st}/>',
        'video': f'<rect x="5.5" y="2" width="9" height="16" rx="2" {st}/><path d="M8.8 7.3v5.4l4-2.7z" fill="{color}"/>',
        'vsl': f'<rect x="2" y="3" width="16" height="11.5" rx="1.5" {st}/><path d="M8.5 6.2v5.1l4-2.55z" fill="{color}"/>'
               f'<path d="M7 17.5h6" {st}/>',
        'artigo': f'<rect x="4" y="2" width="12" height="16" rx="1.5" {st}/><path d="M7 6.5h6M7 9.5h6M7 12.5h4" {st}/>',
        'advert': f'<rect x="2" y="3.5" width="16" height="13" rx="1.5" {st}/><rect x="4.6" y="6.2" width="5" height="4.2" fill="{color}"/>'
                  f'<path d="M11.8 6.8h3.6M11.8 9.6h3.6M4.6 13.3h10.8" {st}/>',
        'lock': f'<rect x="4" y="9" width="12" height="9" rx="2" {st}/><path d="M7 9V6.5a3 3 0 0 1 6 0V9" {st}/>',
        'table': f'<rect x="2.5" y="3.5" width="15" height="13" rx="1.5" {st}/><path d="M2.5 8h15M2.5 12.3h15M8 8v8.5" {st}/>',
        'page': f'<path d="M5 2.5h7l4 4v11H5z" {st}/><path d="M12 2.5v4h4M8 10.5h5M8 13.5h5" {st}/>',
        'ab': f'<rect x="2" y="4" width="7" height="12" rx="1.5" {st}/><rect x="11" y="4" width="7" height="12" rx="1.5" {st}/>'
              f'<path d="M4.3 12.5 5.5 7.5l1.2 5M4.7 11h1.6M13.4 7.5v5h1.5a1.25 1.25 0 0 0 0-2.5h-1.5 1.3a1.25 1.25 0 0 0 0-2.5z" {st.replace(f'stroke-width="{sw}"', 'stroke-width="1.3"')}/>',
        'list': f'<path d="M8 5.5h9M8 10h9M8 14.5h9" {st}/><path d="m2.5 5.5 1.2 1.2 2-2.4M2.5 10l1.2 1.2 2-2.4M2.5 14.5l1.2 1.2 2-2.4" {st}/>',
    }[kind]
    return f'<g transform="translate({x:.1f} {y:.1f}) scale({size / 20:.3f})">{body}</g>'


def header(c, eyebrow, title, subtitle, x=48, y=60, maxw=864):
    c.text(x, y, eyebrow, 'sans7', 13, RED, ls=2.2)
    c.text(x, y + 44, title, 'serif', 34, INK)
    return c.para(x, y + 80, subtitle, 'sans', 17, maxw, 25, INK2)


# ---------------------------------------------------------------- capa

def capa():
    W, H = 1280, 640
    c = Canvas(W, H, 'copymaster',
               'Capa da skill copymaster: copy de resposta direta em português do Brasil, primeiro o diagnóstico, '
               'depois o texto. Ao lado, um rascunho da página de vendas da própria skill: a headline cheia de marketês '
               'riscada a lápis vermelho e reescrita à mão, um depoimento que ainda é placeholder e um post-it com o '
               'diagnóstico.',
               rx=28)
    c.defs.append('<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
                  '<circle cx="2" cy="2" r="1.1" fill="#E6DCCA"/></pattern>'
                  '<filter id="blur" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="12"/></filter>'
                  '<filter id="blur2" x="-30%" y="-100%" width="160%" height="300%"><feGaussianBlur stdDeviation="4"/></filter>')
    c.add(f'<rect width="{W}" height="{H}" fill="url(#dots)"/>')

    # coluna da esquerda
    x0 = 96
    c.add(f'<rect x="{x0}" y="139" width="30" height="3" rx="1.5" fill="{RED}"/>')
    c.text(x0 + 42, 146, 'SKILL PARA O CLAUDE', 'sans7', 15, RED, ls=3)
    size = fit('copymaster', 'serif', 540, 140)
    c.text(x0 - 4, 262, 'copymaster', 'serif', size, INK)
    wc = FONTS['serif'].width('copy', size)
    wa = FONTS['serif'].width('copymaster', size)
    xs, xe = x0 - 4 + wc + 6, x0 - 4 + wa - 4
    c.add(f'<path d="M{xs:.0f} 291 C {xs + (xe - xs) * .3:.0f} 283, {xs + (xe - xs) * .7:.0f} 286, {xe:.0f} 279" '
          f'stroke="{RED}" stroke-width="7" fill="none" stroke-linecap="round"/>')

    y = 352
    for ln in wrap('Copy de resposta direta em português do Brasil.', 'sans6', 27, 520):
        c.text(x0, y, ln, 'sans6', 27, INK)
        y += 37
    c.text(x0, y + 4, 'Primeiro o diagnóstico, depois o texto.', 'sans', 22, INK2)

    chips = [('lp', 'Landing page'), ('site', 'Site'), ('email', 'E-mail'), ('prosp', 'Prospecção'),
             ('video', 'Vídeo'), ('vsl', 'VSL'), ('artigo', 'Artigo'), ('advert', 'Advertorial')]
    cy, cx = y + 34, x0
    for i, (ic, label) in enumerate(chips):
        if i == 4:
            cy, cx = cy + 48, x0
        w = 14 + 18 + 8 + FONTS['sans6'].width(label, 16) + 16
        rect(c, cx, cy, w, 38, WHITE, INK, rx=19)
        c.add(icon(ic, cx + 14, cy + 10, 18, INK))
        c.text(cx + 40, cy + 25, label, 'sans6', 16, INK)
        cx += w + 10
    c.text(x0, H - 42, 'Com base em Schwartz, Masterson & Forde, Sugarman, Bly, Hormozi e Smart Brevity',
           'sans', 14, MUTED)

    # a folha de rascunho
    sw, sh = 420, 532
    c.add('<g transform="translate(895 346) rotate(-4)">')
    c.add(f'<rect x="{-sw / 2 + 8}" y="{-sh / 2 + 16}" width="{sw}" height="{sh}" rx="8" fill="#5A4A30" opacity=".2" filter="url(#blur)"/>')
    c.add(f'<g transform="translate({-sw / 2} {-sh / 2})">')
    rect(c, 0, 0, sw, sh, WHITE, None, rx=8)
    c.text(32, 38, 'Landing page — rascunho 1', 'sans6', 12.5, MUTED)
    c.add(f'<path d="M32 54H{sw - 32}" stroke="#EFE7DA" stroke-width="1.5"/>')
    c.text(32, 92, 'PARA QUEM ESCREVE PARA VENDER', 'sans7', 11, MUTED, ls=1.6)
    for i, ln in enumerate(['A solução definitiva', 'em copywriting com IA']):
        yy = 130 + i * 38
        w = c.text(32, yy, ln, 'serif', 30, INK, op=.42)
        x1, x2, ym = 27, 32 + w + 6, yy - 10
        c.add(f'<path d="M{x1} {ym + 2} C {x1 + (x2 - x1) / 3:.0f} {ym - 3}, {x1 + 2 * (x2 - x1) / 3:.0f} {ym + 3}, {x2:.0f} {ym - 1}" '
              f'stroke="{RED}" stroke-width="3.2" fill="none" stroke-linecap="round"/>')
    # nota de margem: "marketês → fato", com a seta desenhada
    wm = FONTS['hand'].width('marketês', 23)
    wf = FONTS['hand'].width('fato', 23)
    xr = sw - 30
    c.text(xr - wf - 40 - wm, 204, 'marketês', 'hand', 23, RED)
    c.add(f'<path d="M{xr - wf - 34:.0f} 197 h24 m-7 -6 l7 6 l-7 6" stroke="{RED}" stroke-width="2.4" fill="none" '
          f'stroke-linecap="round" stroke-linejoin="round"/>')
    c.text(xr, 204, 'fato', 'hand', 23, RED, anchor='end')
    nova = ['Pare de publicar', 'página que não vende.']
    hs = min(fit(ln, 'hand', sw - 64, 44) for ln in nova)
    for i, ln in enumerate(nova):
        c.text(32, 248 + i * (hs - 2), ln, 'hand', hs, RED)
    w1 = FONTS['hand'].width(nova[0], hs)  # a nota vai depois da linha mais curta
    c.text(32 + w1 + 26, 248, "4 U's", 'hand', 23, RED)
    check(c, 32 + w1 + 26 + FONTS['hand'].width("4 U's", 23) + 8, 240, 0.8, RED, 2.6)
    for i, bw in enumerate([356, 330, 212]):
        rect(c, 32, 318 + i * 18, bw, 8, '#ECE5D8', None, rx=4)
    rect(c, 32, 380, sw - 64, 62, '#FFF5F1', RED, rx=8, sw=1.6, dash='6 5')
    lines = wrap('[DEPOIMENTO: redator que usou a skill num lançamento — nome, resultado e print]', 'sans6', 13, sw - 64 - 36)
    for i, ln in enumerate(lines):
        c.text(50, 380 + 31 - (len(lines) - 1) * 9 + i * 18 + 4, ln, 'sans6', 13, RED_D)
    bt = 'Instalar grátis no Claude Code'
    bw = FONTS['sans7'].width(bt, 15) + 48
    rect(c, 32, 462, bw, 44, INK, None, rx=10)
    c.text(32 + bw / 2, 489, bt, 'sans7', 15, WHITE, anchor='middle')
    c.add('</g></g>')

    # post-it com o diagnóstico
    c.add('<g transform="translate(1148 116) rotate(6)">')
    c.add('<rect x="-98" y="-74" width="204" height="158" fill="#5A4A30" opacity=".18" filter="url(#blur)"/>')
    c.add(f'<rect x="-104" y="-82" width="208" height="160" rx="3" fill="{YELLOW}"/>')
    c.add('<rect x="-36" y="-94" width="72" height="22" fill="#FFFFFF" opacity=".55" transform="rotate(-4)"/>')
    c.text(-84, -36, 'Diagnóstico', 'hand', 31, INK)
    c.add(f'<path d="M-84 -27 C -50 -31, -10 -29, 34 -32" stroke="{INK}" stroke-width="2" fill="none" stroke-linecap="round"/>')
    notes = ['consciente do problema', 'sofisticação: estágio 4', 'ângulo: fuga da dor']
    ns = min(fit(n, 'hand', 172, 23) for n in notes)
    for i, n in enumerate(notes):
        c.text(-84, 2 + i * 27, n, 'hand', ns, INK2)
    c.add('</g>')

    # lápis vermelho
    c.add('<g transform="translate(1066 352) rotate(38)">')
    c.add('<rect x="10" y="12" width="236" height="18" rx="9" fill="#5A4A30" opacity=".22" filter="url(#blur2)"/>')
    c.add('<polygon points="0,0 34,-9 34,9" fill="#F0D2A6"/>')
    c.add(f'<polygon points="0,0 11,-2.9 11,2.9" fill="{RED_D}"/>')
    c.add(f'<rect x="34" y="-9" width="196" height="18" fill="{RED}"/>')
    c.add('<rect x="34" y="-9" width="196" height="5" fill="#E2644E"/>')
    c.add('<rect x="34" y="4" width="196" height="5" fill="#B2341F"/>')
    c.add(f'<rect x="228" y="-9.5" width="16" height="19" rx="3" fill="{INK}"/>')
    c.add('</g>')
    c.save('capa.svg')


# ---------------------------------------------------------------- fluxo

def fluxo():
    W = 960
    c = Canvas(W, 0, 'Como a copymaster trabalha',
               'Seis etapas, nesta ordem: briefing, diagnóstico, grande ideia e abertura, guia do formato, redação e '
               'revisão. Se faltar o essencial no pedido, ela pergunta antes de escrever. A entrega traz o diagnóstico, '
               'a peça pronta, de 3 a 5 variações da abertura para teste A/B e o que conferir antes de publicar.')
    yb = header(c, 'COMO ELA TRABALHA', 'Do pedido à peça pronta, em seis etapas',
                'O texto só começa depois do diagnóstico. Se faltar o essencial no pedido, ela pergunta antes de escrever.')
    steps = [
        ('Briefing', 'O que é o produto, para quem é e o que a peça pede ao leitor.',
         {'note': 'Faltou o essencial? Até 5 perguntas, e ela para.'}),
        ('Diagnóstico', 'Seis eixos decidem a abertura, a ordem dos blocos e o tamanho.',
         {'chips': ['Desejo dominante', 'Dor × prazer', 'Consciência', 'Sofisticação', 'Ceticismo', 'Oferta de entrada']}),
        ('Ideia e abertura', 'A grande ideia numa frase, que a peça inteira prova. A consciência escolhe o tipo de '
         'abertura; a sofisticação, o que ela enfatiza.', {}),
        ('Guia do formato', 'Um dos oito guias de formatos/: estrutura, tamanho, regras do canal e checklist.', {}),
        ('Redação', 'Benefícios, mecanismo, objeções, prova, oferta, garantia e fechamento, cada frase puxando a próxima.', {}),
        ('Revisão', 'Checklists, leitura de quem só passa os olhos, corte de 30% das palavras e CDC, CONAR e LGPD.', {}),
    ]
    cw, gap, pad = 264, 36, 22
    bw = cw - 2 * pad

    def measure(s):
        title, body, extra = s
        h = pad + 32 + 14 + 22 * len(wrap(body, 'sans', 15, bw))
        if 'note' in extra:
            h += 12 + 19 * len(wrap(extra['note'], 'sans6', 13.5, bw - 26))
        if 'chips' in extra:
            rows, x = 1, 0
            for ch in extra['chips']:
                w = FONTS['sans6'].width(ch, 12.5) + 20
                if x and x + w > bw:
                    rows, x = rows + 1, 0
                x += w + 6
            h += 12 + rows * 32 - 6
        return h + pad

    def draw(s, n, x, y, h):
        title, body, extra = s
        rect(c, x, y, cw, h)
        c.add(f'<circle cx="{x + pad + 16}" cy="{y + pad + 16}" r="16" fill="{INK}"/>')
        c.text(x + pad + 16, y + pad + 21.5, str(n), 'sans7', 15, WHITE, anchor='middle')
        c.text(x + pad + 44, y + pad + 22, title, 'sans7', 17.5, INK)
        yy = c.para(x + pad, y + pad + 32 + 14 + 15, body, 'sans', 15, bw, 22, INK2)
        if 'note' in extra:
            yy += 12 + 19
            c.add(f'<circle cx="{x + pad + 9}" cy="{yy - 5}" r="9" fill="{RED}"/>')
            c.text(x + pad + 9, yy - 0.5, '?', 'sans7', 12.5, WHITE, anchor='middle')
            c.para(x + pad + 26, yy, extra['note'], 'sans6', 13.5, bw - 26, 19, RED)
        if 'chips' in extra:
            cx, cy = x + pad, yy + 14
            for ch in extra['chips']:
                w = FONTS['sans6'].width(ch, 12.5) + 20
                if cx > x + pad and cx + w > x + pad + bw:
                    cx, cy = x + pad, cy + 32
                rect(c, cx, cy, w, 26, PAPER2, None, rx=13)
                c.text(cx + 10, cy + 17.5, ch, 'sans6', 12.5, INK)
                cx += w + 6

    top1 = yb + 40
    h1 = max(measure(s) for s in steps[:3])
    h2 = max(measure(s) for s in steps[3:])
    top2 = top1 + h1 + 56
    for row, (top, h) in enumerate([(top1, h1), (top2, h2)]):
        for i in range(3):
            x = 48 + i * (cw + gap)
            draw(steps[row * 3 + i], row * 3 + i + 1, x, top, h)
            if i < 2:
                arrow(c, f'M{x + cw + 8} {top + h / 2} H{x + cw + gap - 8}')
    # do card 3 ao card 4
    x3 = 48 + 2 * (cw + gap) + cw / 2
    x4 = 48 + cw / 2
    ym = top1 + h1 + 28
    arrow(c, f'M{x3} {top1 + h1 + 6} V{ym - 12} Q{x3} {ym} {x3 - 12} {ym} H{x4 + 12} Q{x4} {ym} {x4} {ym + 12} V{top2 - 8}')

    # entrega
    x6 = 48 + 2 * (cw + gap) + cw / 2
    by = top2 + h2 + 44
    arrow(c, f'M{x6} {top2 + h2 + 6} V{by - 8}')
    items = [
        ('table', 'Diagnóstico', 'Os seis eixos em tabela, com a implicação de cada um, a grande ideia e o tipo de abertura.'),
        ('page', 'A peça pronta', 'No formato do canal: seções da página, assunto e corpo, roteiro com tempo e tela.'),
        ('ab', 'Variações A/B', 'De 3 a 5 aberturas com abordagens diferentes; uma entra pelo ângulo oposto.'),
        ('list', 'Antes de publicar', 'As provas que faltam (placeholders), as suposições feitas e até 3 recomendações.'),
    ]
    iw = (864 - 56 - 3 * 24) / 4
    ih = max(len(wrap(d, 'sans', 14, iw)) for _, _, d in items) * 20
    bh = 28 + 30 + 26 + 26 + 12 + ih + 26
    rect(c, 48, by, 864, bh, INK, None, rx=18)
    c.text(76, by + 44, 'O que você recebe', 'serif', 24, WHITE)
    for i, (ic, t, d) in enumerate(items):
        x = 76 + i * (iw + 24)
        y = by + 74
        c.add(f'<circle cx="{x + 16}" cy="{y + 16}" r="16" fill="{RED}"/>')
        c.add(icon(ic, x + 7, y + 7, 18, WHITE, 1.8))
        c.text(x + 42, y + 22, t, 'sans7', 15.5, WHITE)
        c.para(x, y + 56, d, 'sans', 14, iw, 20, '#D8CEBE')
    c.h = by + bh + 44
    c.save('fluxo.svg')


# ---------------------------------------------------------------- consciência

def consciencia():
    W = 960
    c = Canvas(W, 0, 'Nível de consciência e abertura',
               'Escada com os cinco níveis de consciência do leitor, do inconsciente ao mais consciente. Para cada '
               'nível: por onde ele costuma chegar, o tipo de abertura indicado, por onde a peça começa e o tamanho dela. '
               'Quanto mais o leitor já sabe, mais direta e curta a peça.')
    yb = header(c, 'DIAGNÓSTICO', 'O que o leitor já sabe decide por onde a peça começa',
                'Do leitor que nem sabe que tem o problema ao que já quer comprar, mudam a abertura e o tamanho.')
    levels = ['Inconsciente', 'Consciente do problema', 'Consciente da solução', 'Consciente do produto', 'Mais consciente']
    leads = ['História ou Proclamação', 'Problema-Solução ou Grande Segredo', 'Promessa ou Problema-Solução',
             'Promessa, ou Oferta com risco revertido', 'Oferta, com a razão dela']
    chega = ['Anúncio frio em rede social, display, prospecção fria',
             '“Por que [sintoma]”, “como resolver [problema]”, artigo sobre o problema',
             '“Melhor [categoria]”, “como conseguir [resultado]”, quem baixou um material',
             '“X vs Y”, “alternativa a X”, reviews, quem pediu uma demonstração',
             'Busca pela marca, indicação, remarketing, carrinho abandonado, clientes']
    comeca = ['Quem ele é, não o produto', 'O problema nas palavras dele, ou a causa oculta',
              'O resultado desejado e o mecanismo', 'O produto e a superioridade comprovada',
              'O produto, a oferta e a razão da oferta']
    tam = [('Longo, ou 2 etapas', 1.0), ('Longo', .82), ('Médio a longo', .62), ('Médio', .44), ('Curto', .2)]
    ramp = ['#EEE2CD', '#F3C9A6', '#E89670', '#C94A2E', '#A8321F']
    tcol = [INK, INK, INK, WHITE, WHITE]
    cw, gap = 160, 16
    xs = [48 + i * (cw + gap) for i in range(5)]
    inner = cw - 24

    # escada
    top = yb + 64
    hs = []
    for ld in leads:  # cada degrau mais alto que o anterior e com espaço para a abertura
        need = 42 + 18 * (len(wrap(ld, 'sans7', 14, inner)) - 1) + 14
        hs.append(max(need, hs[-1] + 26) if hs else need)
    base = top + 44 + hs[-1]
    arrow(c, f'M{48} {top - 22} H{912}', MUTED, 1.4)
    c.text(48, top - 32, 'FRIO', 'sans7', 11, MUTED, ls=1.6)
    c.text(904, top - 32, 'QUENTE', 'sans7', 11, RED, anchor='end', ls=1.6)
    for i in range(5):
        x, h = xs[i], hs[i]
        lab = wrap(levels[i], 'sans7', 15, cw - 8)
        for j, ln in enumerate(lab):
            c.text(x + 2, base - h - 14 - (len(lab) - 1 - j) * 19, ln, 'sans7', 15, INK)
        c.add(f'<path d="M{x} {base} V{base - h + 10} Q{x} {base - h} {x + 10} {base - h} H{x + cw - 10} '
              f'Q{x + cw} {base - h} {x + cw} {base - h + 10} V{base} Z" fill="{ramp[i]}"/>')
        c.text(x + 12, base - h + 22, 'ABERTURA', 'sans7', 10, tcol[i], ls=1.2, op=.75)
        c.para(x + 12, base - h + 42, leads[i], 'sans7', 14, inner, 18, tcol[i])
    # linhas abaixo
    rows = [('CHEGA POR', chega), ('COMEÇA POR', comeca)]
    y = base + 14
    heights = []
    for label, vals in rows:
        heights.append(18 + max(len(wrap(v, 'sans', 13.5, inner)) for v in vals) * 19 + 10)
    card_h = 14 + sum(heights) + 18 + 34 + 14
    for i in range(5):
        x = xs[i]
        rect(c, x, y, cw, card_h, rx=12)
        yy = y + 14
        for (label, vals), hh in zip(rows, heights):
            c.text(x + 12, yy + 10, label, 'sans7', 10, MUTED, ls=1.2)
            c.para(x + 12, yy + 30, vals[i], 'sans', 13.5, inner, 19, INK2)
            yy += hh
        c.text(x + 12, yy + 10, 'TAMANHO', 'sans7', 10, MUTED, ls=1.2)
        rect(c, x + 12, yy + 20, inner, 6, PAPER2, None, rx=3)
        rect(c, x + 12, yy + 20, inner * tam[i][1], 6, ramp[i] if i > 1 else '#D9B98F', None, rx=3)
        c.text(x + 12, yy + 44, tam[i][0], 'sans6', 13, INK)
    # nota
    ny = y + card_h + 24
    note = ('Consciente, mas cético ou saturado de promessas? A abertura vai para o indireto: '
            'Segredo, Proclamação, História ou Problema-Solução.')
    nl = wrap(note, 'sans6', 15, 864 - 48)
    nh = 22 + len(nl) * 22 + 8 + 18 + 16
    rect(c, 48, ny, 864, nh, CARD, LINE, rx=12)
    c.add(f'<rect x="48" y="{ny}" width="6" height="{nh}" fill="{RED}" rx="3"/>')
    yy = c.para(72, ny + 34, note, 'sans6', 15, 864 - 48, 22, INK)
    c.text(72, yy + 28, 'Níveis de consciência: Eugene Schwartz. Tipos de abertura: Masterson & Forde. '
           'Canais de origem: heurística da skill.', 'sans', 12.5, MUTED)
    c.h = ny + nh + 44
    c.save('consciencia.svg')


# ---------------------------------------------------------------- espinha

def espinha():
    W = 960
    c = Canvas(W, 0, 'A espinha de uma peça de venda',
               'Os oito blocos da maioria das peças de venda, em ordem: atenção, identificação, por que o que ele tentou '
               'não resolveu, a virada e o mecanismo, prova, oferta, garantia e pedido da ação. Uma faixa ao lado mostra '
               'o ângulo: a fuga da dor domina a abertura e os primeiros blocos, e a busca do ganho domina a oferta, a '
               'garantia e o pedido.')
    yb = header(c, 'ESTRUTURA', 'A espinha de uma peça de venda',
                'Cada bloco parte do que o leitor já aceita e abre o próximo. A dor abre a peça; o ganho fecha.')
    blocks = [
        ('Atenção', 'A abertura não precisa vender: precisa fazer ler o trecho seguinte.'),
        ('Identificação', 'Ele se reconhece: a situação e as frustrações, nas palavras dele.'),
        ('Por que nada resolveu', 'O que ele já tentou e o defeito de cada alternativa, com a saída à vista.'),
        ('A virada e o mecanismo', 'Existe outro jeito, com nome. Entra quando a promessa faz o leitor perguntar “como?”.'),
        ('Prova', 'Curta e específica, logo depois da promessa mais ousada, onde a dúvida aparece.'),
        ('Oferta', 'O que ele recebe, o preço depois do valor e a razão do porquê.'),
        ('Garantia', 'O resumo final: os benefícios principais viram condições.'),
        ('Pedido da ação', 'Diz o que acontece, resume a oferta e retoma a promessa da abertura.'),
    ]
    top = yb + 74
    bh, bgap = 50, 10
    xb, bw = 112, 252
    xt = xb + bw + 32
    tw = 912 - xt
    total = len(blocks) * bh + (len(blocks) - 1) * bgap
    # faixa do ângulo
    c.defs.append(f'<linearGradient id="ang" x1="0" y1="0" x2="0" y2="1">'
                  f'<stop offset="0" stop-color="{RED}"/><stop offset=".34" stop-color="{RED}"/>'
                  f'<stop offset=".62" stop-color="{BLUE}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient>')
    rect(c, 64, top, 16, total, 'url(#ang)', None, rx=8)
    c.text(72, top - 16, 'DOR', 'sans7', 11, RED, anchor='middle', ls=1.4)
    c.text(72, top + total + 26, 'GANHO', 'sans7', 11, BLUE, anchor='middle', ls=1.4)
    for i, (t, d) in enumerate(blocks):
        y = top + i * (bh + bgap)
        tip = 10 if i < len(blocks) - 1 else 0
        c.add(f'<path d="M{xb} {y} H{xb + bw} V{y + bh - tip} L{xb + bw / 2} {y + bh} L{xb} {y + bh - tip} Z" fill="{INK}"/>')
        c.text(xb + 18, y + (bh - 10) / 2 + 5.5, f'{i + 1:02d}', 'mono', 12, '#A79C8B')
        c.text(xb + 50, y + (bh - 10) / 2 + 5.5, t, 'sans7', 15.5, WHITE)
        lines = wrap(d, 'sans', 15, tw)
        y0 = y + (bh - 10) / 2 + 5.5 - (len(lines) - 1) * 10
        for j, ln in enumerate(lines):
            c.text(xt, y0 + j * 20, ln, 'sans', 15, INK2)
    # rodapé: duas regras
    ny = top + total + 56
    notes = [
        ('Peça curta comprime a espinha', 'Um e-mail, um anúncio de 30 s ou um cold mail pulam etapas e deixam o resto '
         'para a peça seguinte. O guia de cada formato diz o que fica.'),
        ('Teste da próxima pergunta', 'Ao lado de cada bloco, anote a pergunta que o leitor faz ao terminá-lo. '
         'O bloco seguinte precisa respondê-la.'),
    ]
    nw = (864 - 20) / 2
    nh = 22 + 24 + max(len(wrap(d, 'sans', 14, nw - 44)) for _, d in notes) * 20 + 22
    for i, (t, d) in enumerate(notes):
        x = 48 + i * (nw + 20)
        rect(c, x, ny, nw, nh, rx=12)
        c.text(x + 22, ny + 34, t, 'sans7', 15.5, INK)
        c.para(x + 22, ny + 60, d, 'sans', 14, nw - 44, 20, INK2)
    c.h = ny + nh + 44
    c.save('espinha.svg')


# ---------------------------------------------------------------- arquitetura

def arquitetura():
    W = 960
    c = Canvas(W, 0, 'O que o Claude lê, e quando',
               'Arquitetura da skill. O SKILL.md é lido sempre e indica o guia do formato pedido, um entre oito na '
               'pasta formatos. O método, organizado por tema na pasta references, é lido sob demanda, conforme a etapa. '
               'Opcionalmente, uma base de conhecimento local com os livros e o grafo do graphify é consultada pelo '
               'script kb_lookup.py; ela fica fora do repositório.')
    yb = header(c, 'POR DENTRO', 'O que o Claude lê, e quando',
                'Só o necessário para a peça pedida: um cold mail não carrega as notas de VSL.')
    # pedido
    py = yb + 40
    q = '“Faz a sequência de e-mails do lançamento da minha turma”'
    qw = FONTS['sans6'].width(q, 16) + 40
    c.text(48, py, 'SEU PEDIDO', 'sans7', 11, MUTED, ls=1.6)
    rect(c, 48, py + 12, qw, 46, WHITE, INK, rx=23)
    c.text(68, py + 41, q, 'sans6', 16, INK)

    cols = [200, 238, 370]
    gap = (864 - sum(cols)) / 2
    xs = [48, 48 + cols[0] + gap, 48 + cols[0] + cols[1] + 2 * gap]
    ty = py + 104
    arrow(c, f'M{48 + 40} {py + 64} V{ty - 30}')
    labels = ['1 · SEMPRE', '2 · O GUIA DA PEÇA', '3 · SOB DEMANDA, POR ETAPA']
    for x, lab in zip(xs, labels):
        c.text(x, ty - 12, lab, 'sans7', 11, RED, ls=1.4)
    pad = 18
    # coluna 1
    core = ['Princípios', 'Briefing e diagnóstico', 'Grande ideia e abertura', 'Técnicas de redação',
            'Revisão e entrega', 'Ética e regulação']
    refs = [('aberturas', 'abertura', True), ('estrategia', 'diagnóstico', False),
            ('corpo-do-texto', 'corpo do texto', False), ('leitura-e-gatilhos', 'texto corrido', False),
            ('aplicacao-por-meio', 'outros meios', False), ('fundamentos', 'briefing, títulos', False),
            ('meios-digitais', 'e-mail, web', True), ('brevidade', 'densidade', True),
            ('ofertas', 'oferta', False)]
    forms = ['landing-page', 'site-institucional', 'email', 'prospeccao', 'video', 'vsl', 'artigo', 'advertorial']
    row = 27
    ch = pad + 26 + 24 + len(refs) * row + pad - 4
    for x, w in zip(xs, cols):
        rect(c, x, ty, w, ch)
    for i in range(2):
        arrow(c, f'M{xs[i] + cols[i] + 6} {ty + 40} H{xs[i + 1] - 6}')

    x = xs[0]
    c.text(x + pad, ty + pad + 18, 'SKILL.md', 'mono', 17, INK)
    c.text(x + pad, ty + pad + 42, 'o núcleo de toda peça', 'sans', 13, MUTED)
    for i, it in enumerate(core):
        yy = ty + pad + 50 + 20 + i * row
        c.add(f'<circle cx="{x + pad + 3}" cy="{yy - 4.5}" r="3" fill="{RED}"/>')
        c.text(x + pad + 14, yy, it, 'sans', 13.5, INK2)
    yy = ty + pad + 50 + 20 + len(core) * row + 4
    c.add(f'<path d="M{x + pad} {yy - 16}H{x + cols[0] - pad}" stroke="{LINE}" stroke-width="1.5"/>')
    c.text(x + pad, yy + 4, 'e o roteador: qual guia ler', 'sans6', 13, INK)

    x = xs[1]
    c.text(x + pad, ty + pad + 18, 'formatos/', 'mono', 17, INK)
    c.text(x + pad, ty + pad + 42, 'um guia por peça, lê só um', 'sans', 13, MUTED)
    for i, f in enumerate(forms):
        yy = ty + pad + 50 + 20 + i * row
        on = f == 'email'
        if on:
            rect(c, x + pad - 8, yy - 18, cols[1] - 2 * pad + 16, 25, RED_T, None, rx=6)
        c.text(x + pad, yy, f + '.md', 'mono', 13, RED_D if on else INK2)
        if on:
            c.text(x + cols[1] - pad, yy, 'este pedido', 'sans7', 11.5, RED_D, anchor='end')

    x = xs[2]
    c.text(x + pad, ty + pad + 18, 'references/', 'mono', 17, INK)
    c.text(x + pad, ty + pad + 42, 'o método, por tema, aberto na etapa certa', 'sans', 13, MUTED)
    ms = 12
    for name, stage, _ in refs:
        need = FONTS['mono'].width(name, ms) + 14 + FONTS['sans'].width(stage, 12)
        while need > cols[2] - 2 * pad:
            ms -= 0.25
            need = FONTS['mono'].width(name, ms) + 14 + FONTS['sans'].width(stage, 12)
    for i, (name, stage, on) in enumerate(refs):
        yy = ty + pad + 50 + 20 + i * row
        if on:
            rect(c, x + pad - 8, yy - 18, cols[2] - 2 * pad + 16, 25, RED_T, None, rx=6)
        c.text(x + pad, yy, name, 'mono', ms, RED_D if on else INK2)
        c.text(x + cols[2] - pad, yy, stage, 'sans6' if on else 'sans', 12, RED_D if on else MUTED, anchor='end')

    # base de conhecimento local
    ky = ty + ch + 70
    xc = xs[2] + cols[2] / 2
    arrow(c, f'M{xc} {ty + ch + 6} V{ky - 8}', MUTED, 1.6, '5 5')
    c.text(xc - 14, ty + ch + 40, 'para conferir um ponto no original', 'hand', 21, MUTED, anchor='end')
    kw = 864
    term_w = 420
    left_w = kw - term_w - 3 * 24
    desc = ('Os livros completos em Markdown e o grafo do graphify. A skill funciona sem eles; com eles, confere um '
            'ponto lendo só o trecho, nunca o livro inteiro. O .gitignore mantém a base fora do repositório.')
    dl = wrap(desc, 'sans', 14, left_w)
    kh = max(24 + 26 + 18 + len(dl) * 20 + 22, 4 * 26 + 48)
    rect(c, 48, ky, kw, kh, PAPER2, MUTED, rx=14, sw=1.4, dash='6 5')
    c.add(icon('lock', 70, ky + 22, 20, INK, 1.8))
    c.text(98, ky + 38, 'knowledge-base/', 'mono', 16, INK)
    c.text(98 + FONTS['mono'].width('knowledge-base/', 16) + 12, ky + 38, 'opcional, só na sua máquina', 'sans', 13, MUTED)
    c.para(72, ky + 70, desc, 'sans', 14, left_w, 20, INK2)
    tx = 48 + kw - term_w - 24
    th = kh - 40
    rect(c, tx, ky + 20, term_w, th, INK, None, rx=10)
    lines = [('$ ', 'kb_lookup.py "slippery slide"', '#F3EBDD'),
             ('→ ', 'conceito, livro, linhas e resumo', '#A79C8B'),
             ('$ ', 'kb_lookup.py --read <id>', '#F3EBDD'),
             ('→ ', 'cerca de 80 linhas do trecho', '#A79C8B')]
    ly = ky + 20 + (th - 4 * 26) / 2 + 18
    for i, (p, t, col) in enumerate(lines):
        c.text(tx + 20, ly + i * 26, p, 'mono', 13, RED if p == '$ ' else '#A79C8B')
        c.text(tx + 20 + FONTS['mono'].width(p, 13), ly + i * 26, t, 'mono', 13, col)
    c.h = ky + kh + 44
    c.save('arquitetura.svg')


if __name__ == '__main__':
    capa()
    fluxo()
    consciencia()
    espinha()
    arquitetura()
