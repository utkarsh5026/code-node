"""
The look of code-node's pages: their CSS root class, stylesheet and badge.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..kit.render import _base_css, _page_document, _report_html


# code-node's logo (docs/images/logo.svg): the tab icon of every page, and the served page's /favicon.ico
FAVICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
<path d="M8 16C12 16 12 8 16.5 8" stroke="#60a5fa" stroke-width="2.2" stroke-linecap="round"/>
<path d="M8 16C12 16 12 24 16.5 24" stroke="#f472b6" stroke-width="2.2" stroke-linecap="round"/>
<path d="M19.5 8H24" stroke="#60a5fa" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="0.1 3.2"/>
<path d="M19.5 24H24" stroke="#f472b6" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="0.1 3.2"/>
<rect x="2.5" y="11.5" width="9" height="9" rx="2.6" fill="#9097a3"/>
<circle cx="18" cy="8" r="3.4" fill="#60a5fa"/>
<circle cx="18" cy="24" r="3.4" fill="#f472b6"/>
<circle cx="27" cy="16" r="2.6" fill="#fbbf24"/>
<path d="M21 9.5C24 11 25 13 25.5 14" stroke="#fbbf24" stroke-width="1.6" stroke-linecap="round"/>
</svg>
"""

# inline, so a saved page has its icon too, with nothing beside it
FAVICON_LINK = f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{quote(FAVICON_SVG)}">\n'

_ROOT = "cnd"  # the class around each page's HTML: its stylesheet's rules are scoped to it

_EXTRA_CSS = """\
.cnd .wire{display:grid;grid-template-columns:minmax(0,1fr) 26px minmax(0,.9fr) 26px minmax(0,1fr);align-items:center;margin:6px 0 10px;max-width:980px}
.cnd .wire .wc{display:flex;flex-direction:column;gap:6px;min-width:0}
.cnd .wire .wa{text-align:center;font-size:18px;opacity:.45}
.cnd .wire .wn{border:1px solid rgba(127,127,127,.3);border-radius:8px;padding:5px 10px;line-height:1.35;min-width:0}
.cnd .wire .wn.warn{border-color:rgba(245,158,11,.8);background:rgba(245,158,11,.08)}
.cnd .wire .wn.bad{border-color:rgba(239,68,68,.8);background:rgba(239,68,68,.08)}
.cnd .wire .wn.none{border-style:dashed;opacity:.7}
.cnd .wire .wk{display:block;font-size:10px;font-weight:650;letter-spacing:.05em;text-transform:uppercase;opacity:.6}
.cnd .wire .wn b{display:block;font-weight:600;overflow-wrap:anywhere}
.cnd .wire .wd{display:block;font-size:11.5px;opacity:.7;overflow-wrap:anywhere}
.cnd .wire .wf{border:1px solid rgba(234,88,12,.55);border-radius:10px;padding:10px 12px;background:rgba(234,88,12,.06);text-align:center}
.cnd .wire .wf .wl{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:8px;margin-bottom:4px;color:#fff;font-weight:700;background:linear-gradient(135deg,#f97316,#ea580c)}
.cnd .wire .wf b{display:block;font-size:14px;overflow-wrap:anywhere}
.cnd .colbars{display:flex;align-items:flex-end;gap:2px;height:120px;padding:0 0 0 2px;position:relative;border-bottom:1px solid rgba(127,127,127,.35);max-width:980px}
.cnd .colbars i{flex:1 1 0;min-width:2px;max-width:34px;border-radius:2px 2px 0 0;background:rgba(59,130,246,.55);position:relative;display:flex;flex-direction:column;justify-content:flex-start}
.cnd .colbars i:hover{background:rgba(59,130,246,.8)}
.cnd .colbars i b{display:block;width:100%;border-radius:2px 2px 0 0;background:#ef4444}
.cnd .colbars.dim i{background:rgba(59,130,246,.22);justify-content:flex-end}
.cnd .colbars.dim i b{background:rgba(59,130,246,.75);border-radius:0}
.cnd .colbars .lim{position:absolute;left:0;right:0;border-top:1.5px dashed rgba(239,68,68,.7);pointer-events:none}
.cnd .colbars .lim span{position:absolute;right:0;top:-16px;font-size:10.5px;color:#ef4444;opacity:.85}
.cnd .colbars .top{position:absolute;left:4px;top:-2px;font-size:10.5px;opacity:.55;pointer-events:none}
.cnd .colx{display:flex;justify-content:space-between;font-size:10.5px;opacity:.55;margin:3px 0 10px;max-width:980px}
.cnd .pgw{display:flex;align-items:center;flex-wrap:wrap;gap:4px 12px;margin:8px 0 10px}
.cnd a.pgo{display:inline-block;padding:5px 16px;border:1px solid rgba(59,130,246,.5);border-radius:999px;color:#3b82f6;font-weight:600;font-size:13.5px;text-decoration:none}
.cnd a.pgo:hover{background:rgba(59,130,246,.1)}
.cnd .pgp{font-size:12px;opacity:.65;overflow-wrap:anywhere}
.cnd .flow{border:1px solid rgba(127,127,127,.25);border-radius:8px;padding:6px 10px 6px 4px;margin:4px 0 10px;max-width:1180px;max-height:760px;overflow:auto;font-size:12px}
.cnd .flow .ol{display:flex;align-items:baseline;flex-wrap:wrap;column-gap:8px;row-gap:2px;padding:1px 4px;border-radius:5px;line-height:1.55;min-width:0}
.cnd .flow .ol:hover{background:rgba(127,127,127,.08)}
.cnd .flow .ln{flex:0 0 30px;text-align:right;font:11px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;opacity:.45;user-select:none;-webkit-user-select:none}
.cnd .flow code.ocd{font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:none;padding:0;min-width:0}
.cnd .flow .k-def>code.ocd{font-weight:600}
.cnd .flow .k-return>code.ocd,.cnd .flow .k-raise>code.ocd{font-weight:600}
.cnd .flow .ox{margin-left:38px;padding-left:10px;border-left:1px solid rgba(127,127,127,.28)}
.cnd .flow .nt{display:inline-block;font-size:10.5px;font-weight:600;line-height:1.6;padding:0 7px;border-radius:9px;white-space:nowrap;background:rgba(127,127,127,.14)}
.cnd .flow .nt i{font-style:normal;font-weight:500;opacity:.7;margin-left:4px}
.cnd .flow .n-aws-reads{background:rgba(59,130,246,.16);color:#2f6fdb}
.cnd .flow .n-aws-writes{background:rgba(234,88,12,.16);color:#d0570c}
.cnd .flow .n-aws-sends{background:rgba(219,39,119,.14);color:#c42a73}
.cnd .flow .n-aws-runs{background:rgba(147,51,234,.15);color:#8b3fd9}
.cnd .flow .n-aws-signs{background:rgba(100,116,139,.18)}
.cnd .flow .n-env{background:rgba(13,148,136,.16);color:#0f8a7e}
.cnd .flow .n-event{background:rgba(22,163,74,.15);color:#178a45}
.cnd .flow .n-http{background:rgba(219,39,119,.14);color:#c42a73}
.cnd .flow .n-client{background:rgba(59,130,246,.08);color:#2f6fdb}
.cnd .flow .n-warn,.cnd .flow .n-sleep{background:rgba(245,158,11,.2);color:#b86e04}
.cnd .flow .n-route{background:rgba(147,51,234,.15);color:#8b3fd9}
.cnd .flow .n-log,.cnd .flow .n-file,.cnd .flow .n-command,.cnd .flow .n-more{font-weight:500;opacity:.85}
.cnd .flow details.od{margin:0}
.cnd .flow details.od>summary{list-style:none;cursor:pointer}
.cnd .flow details.od>summary::-webkit-details-marker{display:none}
.cnd .flow .on{white-space:nowrap}
.cnd .flow .on b{font:600 12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.cnd .flow .och{display:inline-block;width:6px;height:6px;margin:0 7px 2px 1px;border-right:1.6px solid currentColor;border-bottom:1.6px solid currentColor;transform:rotate(-45deg);opacity:.6;transition:transform .15s}
.cnd .flow details.od[open]>summary .och{transform:rotate(45deg);margin-bottom:4px}
.cnd .flow details.od[open]>summary .os{display:none}
.cnd .flow .oseen .on{padding-left:15px}
.cnd .flow .of,.cnd .flow .oq{font-size:11px;opacity:.6}
.cnd .flow .oq{font-style:italic}
.cnd .flow .os{display:inline-flex;flex-wrap:wrap;gap:3px 5px}
.cnd .flow .ob{margin-left:22px}
.cnd :is(.flow,.cside) .pk{color:var(--jp-mirror-editor-keyword-color,light-dark(#7c3aed,#c792ea))}
.cnd :is(.flow,.cside) .pf{color:var(--jp-mirror-editor-def-color,light-dark(#2563eb,#82aaff))}
.cnd :is(.flow,.cside) :is(.js,.jk){color:var(--jp-mirror-editor-string-color,light-dark(#047857,#a5d6a7))}
.cnd :is(.flow,.cside) :is(.jn,.jl){color:var(--jp-mirror-editor-number-color,light-dark(#c2410c,#f78c6c))}
.cnd :is(.flow,.cside) .pa{font-style:italic}
.cnd :is(.flow,.cside) .pc{opacity:.6;font-style:italic}
.cnd .cgb{width:fit-content;max-width:min(100%,1180px)}
.cnd .cg{border:1px solid rgba(127,127,127,.2);border-radius:14px;margin:6px 0 8px;overflow:auto;background-color:rgba(127,127,127,.035);background-attachment:local;background-size:18px 18px;
 background-image:radial-gradient(circle at 1px 1px,rgba(127,127,127,.3) 1px,transparent 0);background-position:9px 9px}
.cnd .cg svg{display:block;max-width:100%;height:auto;overflow:visible;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.cnd .cg .cap{font-size:12px;font-weight:650;letter-spacing:1.2px;fill:currentColor;fill-opacity:.6}
.cnd .cg .capl{stroke:currentColor;stroke-opacity:.14;stroke-width:1;fill:none}
.cnd .cg .cn,.cnd .cg .ce{transition:opacity .15s}
.cnd .cg .cn .bg{fill:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke:none;filter:drop-shadow(0 1px 1.5px rgba(0,0,0,.07)) drop-shadow(0 6px 16px rgba(15,23,42,.07))}
.cnd .cg .cn .fg{fill:rgba(255,255,255,.05);stroke:rgba(127,127,127,.32);stroke-width:1}
.cnd .cg .cn:hover .fg{stroke:rgba(127,127,127,.6)}
.cnd .cg .cn text{fill:currentColor}
.cnd .cg .cn .lb{font-size:14px;font-weight:650;letter-spacing:-.1px}
.cnd .cg .k-handler .lb,.cnd .cg .k-function .lb{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;font-size:13.5px;font-weight:650;letter-spacing:0}
.cnd .cg .k-handler .lb{font-size:14px;font-weight:700}
.cnd .cg .cn .sb{font-size:12.5px;fill-opacity:.62}
.cnd .cg .cn .sb .dir{fill-opacity:.4}
.cnd .cg .cn .sb .ac{font-weight:600;fill-opacity:.95}
.cnd .cg .cn .sb .sep{fill-opacity:.4}
.cnd .cg .cn .dv{stroke:rgba(127,127,127,.2);stroke-width:1;fill:none}
.cnd .cg .cn .rw{font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;fill-opacity:.88}
.cnd .cg .cn .rw.mo{font-family:inherit;font-style:italic;fill-opacity:.55}
.cnd .cg .cn .pr{font-size:12.5px;fill-opacity:.7}
.cnd .cg .cn .ns{font-size:12px;font-weight:650;fill:light-dark(#b45309,#fbbf24);letter-spacing:.2px}
.cnd .cg .cn .bu{fill:var(--c,rgba(127,127,127,.6))}
.cnd .cg .cn .bdg{fill:var(--t,rgba(127,127,127,.12));stroke:var(--c,rgba(127,127,127,.5));stroke-opacity:.22;stroke-width:1}
.cnd .cg .cn .ico{fill:none;stroke:var(--c,currentColor);stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.cnd .cg .k-event{--c:#16a34a;--t:rgba(22,163,74,.12)}
.cnd .cg .k-env{--c:#0d9488;--t:rgba(13,148,136,.13)}
.cnd .cg .k-aws{--c:#3b82f6;--t:rgba(59,130,246,.12)}
.cnd .cg .k-http{--c:#db2777;--t:rgba(219,39,119,.11)}
.cnd .cg .k-start{--c:#64748b;--t:rgba(100,116,139,.13)}
.cnd .cg .k-function{--c:currentColor;--t:rgba(127,127,127,.12)}
.cnd .cg .k-function .ico{stroke-opacity:.72}
.cnd .cg .k-aws .bu,.cnd .cg .k-http .bu{fill:rgba(127,127,127,.55)}
.cnd .cg .k-start .fg{stroke-dasharray:5 4;stroke:rgba(127,127,127,.55);fill:rgba(127,127,127,.04)}
.cnd .cg .k-start .bg{filter:none}
.cnd .cg .k-handler .bg{filter:drop-shadow(0 1px 2px rgba(0,0,0,.1)) drop-shadow(0 10px 24px rgba(15,23,42,.12))}
.cnd .cg .k-handler .fg{stroke:currentColor;stroke-opacity:.6;stroke-width:1.5}
.cnd .cg .k-handler .bdg{fill:currentColor;stroke:none}
.cnd .cg .k-handler .ico{stroke:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke-width:1.7}
.cnd .cg .cn.warn .fg{stroke:#f59e0b;stroke-opacity:1;stroke-width:1.5;fill:rgba(245,158,11,.06)}
.cnd .cg .wb circle,.cnd .cg .wm circle{fill:#f59e0b;stroke:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke-width:1.5}
.cnd .cg .wb path,.cnd .cg .wm path{stroke:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke-width:2;stroke-linecap:round;fill:none}
.cnd .cg .rt rect{fill:rgba(127,127,127,.1);stroke:rgba(127,127,127,.22)}
.cnd .cg .rt text{font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;fill-opacity:.85}
.cnd .cg .rt .mt{font-weight:700;fill-opacity:1}
.cnd .cg .ce path{fill:none}
.cnd .cg .ce .ln{stroke:var(--c);stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.cnd .cg .ce .ah{fill:var(--c);stroke:var(--c);stroke-width:.6;stroke-linejoin:round}
.cnd .cg .ce .hit{stroke:transparent;stroke-width:12}
.cnd .cg .ce .halo{stroke:#f59e0b;stroke-opacity:.75;stroke-width:7;stroke-linecap:round;stroke-linejoin:round}
.cnd .cg .ce .cs{stroke:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke-width:3.4;stroke-linecap:round;stroke-linejoin:round}
.cnd .cg .ce:hover .ln{stroke-width:2.6}
.cnd .cg .ce.pt circle{fill:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke:var(--c);stroke-width:1.6}
.cnd .cg .ce .lpb circle{fill:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke:var(--c);stroke-width:1.3}
.cnd .cg .ce .lpb path{fill:none;stroke:var(--c);stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}
.cnd .cg .ek-call,.cnd .cgk .ek-call,.cnd .cgk .ek-guess,.cnd .cgk .ek-via{--c:rgba(127,127,127,.95)}
.cnd .cg .ek-event{--c:#16a34a}
.cnd .cg .ek-event .ln{stroke-width:2.2}
.cnd .cg .ek-env,.cnd .cgk .ek-env{--c:#0d9488}
.cnd .cg .ek-env .ln,.cnd .cgk .ek-env .ln{stroke-dasharray:5 4}
.cnd .cg .ek-client,.cnd .cgk .ek-client{--c:rgba(100,116,139,.85)}
.cnd .cg .ek-client .ln,.cnd .cgk .ek-client .ln{stroke-dasharray:.5 4.5;stroke-width:2}
.cnd .cg .ek-reads,.cnd .cgk .ek-reads{--c:#3b82f6}
.cnd .cg .ek-writes,.cnd .cgk .ek-writes{--c:#ea580c}
.cnd .cg .ek-sends,.cnd .cg .ek-http,.cnd .cgk .ek-sends,.cnd .cgk .ek-http{--c:#db2777}
.cnd .cg .ek-runs,.cnd .cgk .ek-runs{--c:#9333ea}
.cnd .cg .ek-signs,.cnd .cgk .ek-signs{--c:rgba(100,116,139,.9)}
.cnd .cg .ek-signs .ln,.cnd .cgk .ek-signs .ln{stroke-dasharray:6 3}
.cnd .cg .ek-http .ln,.cnd .cgk .ek-http .ln{stroke-dasharray:8 3}
.cnd .cg .ce.guess .ln,.cnd .cgk .ek-guess .ln{stroke-dasharray:3 2.5;stroke-linecap:butt}
.cnd .cg .ce.via .ln,.cnd .cgk .ek-via .ln{stroke-dasharray:9 3 2 3}
.cnd .cg .cn .ac{fill:var(--c)}
.cnd .cg .cn .sb .ek-reads{fill:light-dark(#2563eb,#60a5fa)}.cnd .cg .cn .sb .ek-writes{fill:light-dark(#c2410c,#fb923c)}
.cnd .cg .cn .sb .ek-sends{fill:light-dark(#be185d,#f472b6)}.cnd .cg .cn .sb .ek-runs{fill:light-dark(#7e22ce,#c084fc)}
.cnd .cg .cn .sb .ek-signs{fill:light-dark(#475569,#94a3b8)}
.cnd .cg .cn .bu.flagged{fill:#f59e0b}
.cnd .cgk{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 12px;width:0;min-width:100%;font-size:12px}
.cnd .cgk .kp{display:inline-flex;align-items:center;gap:6px;padding:3px 10px 3px 8px;border:1px solid rgba(127,127,127,.25);border-radius:999px;background:rgba(127,127,127,.05);line-height:16px;white-space:nowrap}
.cnd .cgk .kp b{font-weight:650;margin-right:3px}
.cnd .cgk .kh{border-style:dashed;white-space:normal}
.cnd .cgk .kt{opacity:.55;margin-left:auto;padding:3px 2px}
.cnd .cgk .sw{display:block;overflow:visible;flex:none}
.cnd .cgk .sw .ln{fill:none;stroke:var(--c);stroke-width:1.8;stroke-linecap:round}
.cnd .cgk .sw .ah{fill:var(--c);stroke:var(--c);stroke-width:.6;stroke-linejoin:round}
.cnd .cgk .kw circle{fill:#f59e0b}
.cnd .cgk .kw path{stroke:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));stroke-width:1.8;stroke-linecap:round;fill:none}
.cnd .cgk .kl circle{fill:none;stroke:currentColor;stroke-opacity:.55;stroke-width:1.2}
.cnd .cgk .kl path{fill:none;stroke:currentColor;stroke-opacity:.8;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}
.cnd .cg a.cl{cursor:pointer;outline:none}
.cnd .cg a.cl:focus-visible .fg{stroke:light-dark(#2563eb,#60a5fa);stroke-opacity:1;stroke-width:2}
.cnd .cside{position:fixed;top:0;right:0;bottom:0;z-index:30;box-sizing:border-box;width:min(660px,94vw);overflow:auto;padding:0 20px 28px;background:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));color:CanvasText;border-left:1px solid rgba(127,127,127,.3);box-shadow:-14px 0 36px rgba(15,23,42,.14);transform:translateX(104%);visibility:hidden;transition:transform .22s ease,visibility 0s linear .22s}
.cnd .cside:target{transform:none;visibility:visible;transition:transform .22s ease}
.cnd .cside .csh{display:flex;align-items:flex-start;gap:12px;position:sticky;top:0;z-index:1;margin:0 -20px 12px;padding:16px 20px 12px;background:var(--jp-layout-color0,var(--vscode-editor-background,Canvas));border-bottom:1px solid rgba(127,127,127,.2)}
.cnd .cside .cst{flex:1;min-width:0}
.cnd .cside .csk{display:block;font-size:11px;font-weight:650;letter-spacing:.08em;text-transform:uppercase;opacity:.55}
.cnd .cside .csn{display:block;font-size:17px;font-weight:650;overflow-wrap:anywhere;margin:2px 0 1px}
.cnd .cside .csn.mono{font:650 16px ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
.cnd .cside .css{font-size:12.5px;opacity:.65;overflow-wrap:anywhere}
.cnd .cside a.csx{flex:none;display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:8px;font-size:22px;line-height:1;color:inherit;text-decoration:none;opacity:.6}
.cnd .cside a.csx:hover,.cnd .cside a.csx:focus-visible{opacity:1;background:rgba(127,127,127,.14)}
.cnd .cside .csd{font-size:13px;line-height:1.5;margin:0 0 6px;opacity:.82;overflow-wrap:anywhere}
.cnd .cside .csl{font-size:12px;opacity:.6}
.cnd .cside .csw{font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;margin:16px 0 5px;overflow-wrap:anywhere}
.cnd .cside .csw span{opacity:.55}
.cnd .cside pre.csc{margin:0;padding:8px 0;border:1px solid rgba(127,127,127,.22);border-radius:8px;overflow:auto;background:rgba(127,127,127,.04);font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
.cnd .cside .sl{display:block;width:max-content;min-width:100%;box-sizing:border-box;padding-right:14px;white-space:pre}
.cnd .cside .sl.lit{background:rgba(245,158,11,.16);box-shadow:inset 3px 0 #f59e0b}
.cnd .cside .sn{display:inline-block;width:3.2em;padding-right:14px;text-align:right;opacity:.42;user-select:none;-webkit-user-select:none}
.cnd .cside .csm{font-size:12px;font-style:italic;opacity:.6;margin:6px 2px 0}
@media (min-width:1100px){.cnd:has(.cside:target){margin-right:min(660px,94vw)}}
@media (prefers-reduced-motion:reduce){.cnd .cside,.cnd .cside:target{transition:none}}"""

_CSS = _base_css(_ROOT, _EXTRA_CSS)

_BADGE = "◆ code-node"  # the chip before each page's title

_WIDE_CSS = """\
<style>
.cnd .flow{max-width:none;max-height:none}
.cnd .cgb{max-width:100%}
</style>
"""


def render_page(blocks: list[Any], title: str) -> str:
    """
    A report as a whole HTML document to open in a browser tab, with no row cap: the outline and the graph are as
    wide and tall as they are instead of scrolling in a box.
    """
    return _page_document(_report_html(blocks, 0, _CSS + _WIDE_CSS, _ROOT, _BADGE), title, FAVICON_LINK)
