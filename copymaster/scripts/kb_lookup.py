#!/usr/bin/env python3
"""Busca na base de conhecimento local da skill (livros em .md + grafo do graphify).

A base fica fora do repositório público: crie um link `knowledge-base/` dentro da
pasta da skill apontando para a sua pasta de livros, ou defina COPYMASTER_KB.

Uso:
  kb_lookup.py "termo de busca" [--max 8]   conceitos do grafo que batem com o termo
  kb_lookup.py --read ID [--lines 80]       imprime o trecho do livro de um conceito
  kb_lookup.py --grep "regex" [--max 20]    busca literal nos livros (.md), com o número da linha
  kb_lookup.py --communities                lista os temas (comunidades) do grafo

Os conceitos do grafo têm rótulos em inglês (como nos livros); busque com os termos
originais (ex.: "slippery slide", "lead", "guarantee", "e-mail", "advertorial").
"""
import argparse, json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def kb_dir(arg):
    for cand in (arg, os.environ.get('COPYMASTER_KB'), os.path.join(SKILL, 'knowledge-base')):
        if cand and os.path.isdir(cand):
            return cand
    return None


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return s.lower()


def load_graph(kb):
    p = os.path.join(kb, 'graphify-out', 'graph.json')
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding='utf-8'))


def book_path(kb, source_file):
    p = os.path.join(kb, source_file)
    if source_file.endswith('.pdf'):          # prefer the Markdown conversion when one exists
        stem = re.split(r' -- ', source_file)[0]
        for f in os.listdir(kb):
            if f.endswith('.md') and norm(stem)[:12] in norm(f):
                return os.path.join(kb, f)
    return p


def search(g, query, maxn):
    terms = [t for t in re.split(r'\W+', norm(query)) if t]
    adj = {}
    for e in g['links']:
        adj.setdefault(e['source'], []).append((e['target'], e.get('relation', '')))
        adj.setdefault(e['target'], []).append((e['source'], e.get('relation', '')))
    byid = {n['id']: n for n in g['nodes']}
    scored = []
    for n in g['nodes']:
        label, rat = norm(n.get('label')), norm(n.get('rationale'))
        if not all(t in label + ' ' + rat + ' ' + norm(n.get('community_name')) for t in terms):
            continue
        score = sum(3 for t in terms if t in label) + sum(1 for t in terms if t in rat) + len(adj.get(n['id'], [])) / 50
        scored.append((score, n))
    scored.sort(key=lambda x: -x[0])
    for _, n in scored[:maxn]:
        print(f"● {n['label']}  [id: {n['id']}]")
        print(f"  {n.get('source_file')} · {n.get('source_location') or 's/ linha'} · tema: {n.get('community_name')}")
        if n.get('rationale'):
            print(f"  {n['rationale']}")
        rel = [f"{byid[t]['label']} ({r})" for t, r in adj.get(n['id'], [])[:6] if t in byid]
        if rel:
            print('  ligado a: ' + '; '.join(rel))
        print()
    if not scored:
        print('Nada no grafo. Tente outro termo (em inglês) ou --grep.')


def read(kb, g, node_id, nlines):
    n = next((x for x in g['nodes'] if x['id'] == node_id), None)
    if not n or not n.get('source_location'):
        sys.exit('Conceito sem localização no livro.')
    m = re.match(r'L(\d+)(?:-L(\d+))?', n['source_location'])
    a = int(m.group(1)); b = int(m.group(2) or a)
    a = max(1, a - 3); b = min(max(b, a + 20) + 3, a + nlines)
    path = book_path(kb, n['source_file'])
    with open(path, encoding='utf-8') as fh:
        lines = fh.readlines()
    print(f"# {n['label']} — {os.path.basename(path)}, linhas {a}–{b}\n")
    for i in range(a - 1, min(b, len(lines))):
        print(f"{i + 1:6}  {lines[i].rstrip()}")


def grep(kb, pattern, maxn):
    rx = re.compile(pattern, re.I)
    hits = 0
    for f in sorted(os.listdir(kb)):
        if not f.endswith('.md'):
            continue
        with open(os.path.join(kb, f), encoding='utf-8') as fh:
            for i, line in enumerate(fh, 1):
                if rx.search(line):
                    print(f"{f}:{i}: {line.strip()[:200]}")
                    hits += 1
                    if hits >= maxn:
                        return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('query', nargs='?')
    ap.add_argument('--kb')
    ap.add_argument('--max', type=int, default=8)
    ap.add_argument('--read')
    ap.add_argument('--lines', type=int, default=80)
    ap.add_argument('--grep')
    ap.add_argument('--communities', action='store_true')
    a = ap.parse_args()
    kb = kb_dir(a.kb)
    if not kb:
        print('Base de conhecimento local não encontrada (knowledge-base/ ou COPYMASTER_KB). Use só as referências.')
        return
    if a.grep:
        return grep(kb, a.grep, a.max if a.max != 8 else 20)
    g = load_graph(kb)
    if g is None:
        print('Sem graphify-out/graph.json na base; use --grep.')
        return
    if a.communities:
        seen = {}
        for n in g['nodes']:
            seen[n.get('community_name')] = seen.get(n.get('community_name'), 0) + 1
        for k, v in sorted(seen.items(), key=lambda x: -x[1]):
            print(f"{v:4}  {k}")
        return
    if a.read:
        return read(kb, g, a.read, a.lines)
    if not a.query:
        ap.print_help(); return
    search(g, a.query, a.max)


if __name__ == '__main__':
    main()
