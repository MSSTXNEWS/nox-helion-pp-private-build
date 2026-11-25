S=/workspace/nox/web/site
cd $S
[ -f nox-home-v.css ] && cp -p nox-home-v.css nox-home-v.css.bak_s1_$(date +%H%M%S)
base64 -d > nox-home-v.css <<'S1EOF'
LyogTk9YIMK3INCT0LvQsNCy0L3QsNGPINCyINGA0LDRgdC60LvQsNC00LrQtSB2aXNpb25PUyBIb21lICsgUmF5Y2FzdC9MaW5lYXIgZGFzaGJvYXJkOiDQv9GA0LjQstC10YLRgdGC0LLQuNC1LCDQutGA0YPQv9C90YvQuSDQt9Cw0L/RgNC+0YEsINC/0LvQuNGC
0LrQuCDQtNC10LnRgdGC0LLQuNC5LCDQttC40LLRi9C1INC60LDRgNGC0L7Rh9C60LgsINGB0L7QsdGL0YLQuNGPLiDQotC+0LvRjNC60L4g0YHRgtC40LvQuCDQv9C+0LLQtdGA0YUgbm94LWhvbWUteC5jc3MuICovCmJvZHlbZGF0YS1wYWdlPWhvbWVdey0taHYt
cjoyMHB4Oy0taHYtZzpyZ2JhKDE0LDksOSwuNjIpOy0taHYtYjpyZ2JhKDI1NSwxNjAsMTIwLC4xNil9CkBtZWRpYSAobWluLXdpZHRoOjIyMDBweCl7Ym9keVtkYXRhLXBhZ2U9aG9tZV0gLnBhZ2V7em9vbToxLjV9fQpAbWVkaWEgKG1pbi13aWR0aDozMDAwcHgp
e2JvZHlbZGF0YS1wYWdlPWhvbWVdIC5wYWdle3pvb206Mn19CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC53cmFwe3dpZHRoOm1pbigxMTgwcHgsY2FsYygxMDAlIC0gNDBweCkpO2dhcDoxNHB4fQpib2R5W2RhdGEtcGFnZT1ob21lXSAucGh7cGFkZGluZzowO21hcmdp
bjowfQpib2R5W2RhdGEtcGFnZT1ob21lXSAucGg+ZGl2OmZpcnN0LWNoaWxke2Rpc3BsYXk6bm9uZX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLnBoe2p1c3RpZnktY29udGVudDpmbGV4LWVuZDttYXJnaW4tYm90dG9tOi02cHg7cG9zaXRpb246cmVsYXRpdmU7ei1p
bmRleDoyfQpib2R5W2RhdGEtcGFnZT1ob21lXSAucGggLmFjdHMgLnRhZ3tkaXNwbGF5Om5vbmV9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5waCAuc2Vne2JhY2tncm91bmQ6bm9uZTtib3JkZXI6MDtib3gtc2hhZG93Om5vbmU7LXdlYmtpdC1iYWNrZHJvcC1maWx0
ZXI6bm9uZTtiYWNrZHJvcC1maWx0ZXI6bm9uZX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gI3JlZnJlc2h7bWluLWhlaWdodDozNHB4O3BhZGRpbmc6MCAxNHB4O2JvcmRlci1yYWRpdXM6MTdweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWh2LWIpO2JhY2tncm91bmQ6
cmdiYSgyNTUsMTQwLDEwMCwuMDcpO2ZvbnQtc2l6ZToxMC41cHg7bGV0dGVyLXNwYWNpbmc6LjE0ZW07Y29sb3I6dmFyKC0tbXUsI2MyYTlhMCl9CmJvZHlbZGF0YS1wYWdlPWhvbWVdICNyZWZyZXNoOjpiZWZvcmUsYm9keVtkYXRhLXBhZ2U9aG9tZV0gI3JlZnJl
c2g6OmFmdGVye2Rpc3BsYXk6bm9uZX0KLyog0L7QsdGJ0LXQtSDRgdGC0LXQutC70L4g0LrQsNGA0YLQvtGH0LXQuiAqLwpib2R5W2RhdGEtcGFnZT1ob21lXSAuY2FyZCxib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtZ2xhc3N7Ym9yZGVyLXJhZGl1czp2YXIoLS1o
di1yKTtiYWNrZ3JvdW5kOnZhcigtLWh2LWcpO2JvcmRlcjoxcHggc29saWQgdmFyKC0taHYtYik7LXdlYmtpdC1iYWNrZHJvcC1maWx0ZXI6Ymx1cigyNnB4KSBzYXR1cmF0ZSgxLjM1KTtiYWNrZHJvcC1maWx0ZXI6Ymx1cigyNnB4KSBzYXR1cmF0ZSgxLjM1KTti
b3gtc2hhZG93Omluc2V0IDAgMXB4IDAgcmdiYSgyNTUsMjU1LDI1NSwuMDcpLDAgMThweCA1MHB4IHJnYmEoMCwwLDAsLjM1KX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmNhcmQ6OmJlZm9yZSxib2R5W2RhdGEtcGFnZT1ob21lXSAuY2FyZDo6YWZ0ZXJ7ZGlzcGxh
eTpub25lfQovKiDQv9GA0LjQstC10YLRgdGC0LLQuNC1ICsg0YHRgtGA0L7QutCwINC30LDQv9GA0L7RgdCwICovCmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1oZXJvPip7bWluLXdpZHRoOjB9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1xYXtncmlkLXRlbXBs
YXRlLWNvbHVtbnM6cmVwZWF0KDYsbWlubWF4KDAsMWZyKSl9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1oZXJve2dyaWQtdGVtcGxhdGUtY29sdW1uczptaW5tYXgoMCwxLjZmcikgbWlubWF4KDAsMWZyKTtnYXA6MTRweDttYXJnaW46MH0KYm9keVtkYXRhLXBh
Z2U9aG9tZV0gLmh4LWhpe3BhZGRpbmc6MjZweCAyOHB4IDIycHg7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgta2lja3tmb250LXNpemU6MTBweDtsZXR0ZXIt
c3BhY2luZzouMzJlbTtvcGFjaXR5Oi44fQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtaHttYXJnaW46OHB4IDAgNnB4O2ZvbnQ6MzAwIGNsYW1wKDI4cHgsMy40dncsNDRweCkvMS4wOCB2YXIoLS1oZWFkLGluaGVyaXQpO2xldHRlci1zcGFjaW5nOi4xNGVtfQpi
b2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtc3Vie21hcmdpbjowIDAgMjBweDtmb250LXNpemU6MTRweDtjb2xvcjojZDljMmI2fQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNre3Bvc2l0aW9uOnJlbGF0aXZlO2dhcDowO2ZsZXgtd3JhcDpub3dyYXA7YWxpZ24t
aXRlbXM6Y2VudGVyO21pbi1oZWlnaHQ6NjJweDtwYWRkaW5nOjZweCA2cHggNnB4IDU0cHg7Ym9yZGVyLXJhZGl1czoyMHB4O2JhY2tncm91bmQ6cmdiYSg4LDUsNSwuNTUpO2JvcmRlcjoxcHggc29saWQgcmdiYSgyNTUsMTYwLDEyMCwuMjgpO2JveC1zaGFkb3c6
aW5zZXQgMCAxcHggMCByZ2JhKDI1NSwyNTUsMjU1LC4wNiksMCAxMHB4IDM0cHggcmdiYSgwLDAsMCwuMzUpO3RyYW5zaXRpb246Ym9yZGVyLWNvbG9yIC4xNXMsYm94LXNoYWRvdyAuMTVzfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrOmZvY3VzLXdpdGhp
bntib3JkZXItY29sb3I6cmdiYSh2YXIoLS1jeSksLjcpO2JveC1zaGFkb3c6MCAwIDAgM3B4IHJnYmEodmFyKC0tY3kpLC4xNCksMCAxMHB4IDM0cHggcmdiYSgwLDAsMCwuMzUpfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrOjpiZWZvcmV7Y29udGVudDon
Jztwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjIwcHg7dG9wOjUwJTt3aWR0aDoxNXB4O2hlaWdodDoxNXB4O21hcmdpbi10b3A6LTlweDtib3JkZXI6MnB4IHNvbGlkIHZhcigtLW11LCNjMmE5YTApO2JvcmRlci1yYWRpdXM6NTAlfQpib2R5W2RhdGEtcGFnZT1ob21l
XSAuaHgtYXNrOjphZnRlcntjb250ZW50OicnO3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6MzNweDt0b3A6NTAlO3dpZHRoOjdweDtoZWlnaHQ6MnB4O21hcmdpbi10b3A6NnB4O2JhY2tncm91bmQ6dmFyKC0tbXUsI2MyYTlhMCk7dHJhbnNmb3JtOnJvdGF0ZSg0NWRl
Zyk7Ym9yZGVyLXJhZGl1czoxcHh9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2sgaW5wdXR7ZmxleDoxIDEgYXV0bzttaW4td2lkdGg6MDttaW4taGVpZ2h0OjQ4cHg7cGFkZGluZzowIDhweDtib3JkZXI6MDtiYWNrZ3JvdW5kOm5vbmU7Zm9udDo0MDAgMThw
eCB2YXIoLS1ib2R5LGluaGVyaXQpO2NvbG9yOiNmZmZ9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2sgaW5wdXQ6OnBsYWNlaG9sZGVye2NvbG9yOnZhcigtLW11MiwjOWM4Mjc5KX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWFzayBidXR0b257bWluLWhl
aWdodDo0NnB4O3BhZGRpbmc6MCAyMHB4O2JvcmRlci1yYWRpdXM6MTVweDttYXJnaW4tbGVmdDo2cHg7Zm9udDo2MDAgMTJweC8xIHZhcigtLWJvZHksaW5oZXJpdCk7bGV0dGVyLXNwYWNpbmc6LjA2ZW07dGV4dC10cmFuc2Zvcm06bm9uZTtjb2xvcjojZmZmM2Vh
O2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDE2MGRlZyxyZ2IodmFyKC0tYW0pKSxyZ2IodmFyKC0tY3kpKSk7Ym9yZGVyOjA7Ym94LXNoYWRvdzowIDRweCAxOHB4IHJnYmEodmFyKC0tY3kpLC4zKX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWFzayBidXR0
b24uYWx0e2JhY2tncm91bmQ6cmdiYSgyNTUsMjU1LDI1NSwuMDcpO2JveC1zaGFkb3c6bm9uZTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWh2LWIpO2NvbG9yOiNmMWRmZDZ9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1oaXRze21hcmdpbi10b3A6MTJweH0KLyog
0YHQvtCx0YvRgtC40Y8g0LrQsNC6INC70LXQvdGC0LAgTGluZWFyICovCmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1ldntwYWRkaW5nOjIwcHggMjJweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1ufQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgt
ZXYgaDN7bWFyZ2luOjAgMCA4cHg7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjI2ZW19CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1le3BhZGRpbmc6OXB4IDAgOXB4IDE2cHg7cG9zaXRpb246cmVsYXRpdmU7Ym9yZGVyLXRvcDoxcHggc29saWQgcmdi
YSgyNTUsMTYwLDEyMCwuMDkpO2ZvbnQtc2l6ZToxM3B4fQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtZTo6YmVmb3Jle2NvbnRlbnQ6Jyc7cG9zaXRpb246YWJzb2x1dGU7bGVmdDowO3RvcDoxNXB4O3dpZHRoOjZweDtoZWlnaHQ6NnB4O2JvcmRlci1yYWRpdXM6
NTAlO2JhY2tncm91bmQ6cmdiKHZhcigtLWFtKSk7Ym94LXNoYWRvdzowIDAgOHB4IHJnYmEodmFyKC0tYW0pLC42KX0KLyog0L/Qu9C40YLQutC4INCx0YvRgdGC0YDRi9GFINC00LXQudGB0YLQstC40LkgKHZpc2lvbk9TKSAqLwpib2R5W2RhdGEtcGFnZT1ob21l
XSAuaHgta3ttYXJnaW46NnB4IDRweCAwO2ZvbnQtc2l6ZToxMHB4O2xldHRlci1zcGFjaW5nOi4zZW19CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1xYXtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KGF1dG8tZmlsbCxtaW5tYXgoMTA0cHgsMWZyKSk7Z2Fw
OjEycHg7bWFyZ2luOjB9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1xYSBhe2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2dhcDo5cHg7bWluLWhlaWdodDoxMDBweDtwYWRkaW5nOjEycHggNnB4O2JvcmRlci1yYWRpdXM6MjRw
eDt0ZXh0LWFsaWduOmNlbnRlcjtmb250OjUwMCAxMS41cHgvMS4yIHZhcigtLWJvZHksaW5oZXJpdCk7bGV0dGVyLXNwYWNpbmc6LjAyZW07dGV4dC10cmFuc2Zvcm06bm9uZTtjb2xvcjojZjFkZmQ2O3RyYW5zaXRpb246dHJhbnNmb3JtIC4xOHMgY3ViaWMtYmV6
aWVyKC4yLC44LC4yLDEpLGJhY2tncm91bmQgLjE1cyxib3JkZXItY29sb3IgLjE1c30KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LXFhIGEgc2wtaWNvbntmb250LXNpemU6MjhweDtjb2xvcjojZmZkOWM0O3dpZHRoOjUycHg7aGVpZ2h0OjUycHg7ZGlzcGxheTpn
cmlkO3BsYWNlLWl0ZW1zOmNlbnRlcjtib3JkZXItcmFkaXVzOjE2cHg7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoMTYwZGVnLHJnYmEodmFyKC0tYW0pLC4yOCkscmdiYSh2YXIoLS1jeSksLjE4KSk7Ym94LXNoYWRvdzppbnNldCAwIDFweCAwIHJnYmEoMjU1
LDI1NSwyNTUsLjE4KX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LXFhIGE6aG92ZXJ7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoLTNweCkgc2NhbGUoMS4wMyk7YmFja2dyb3VuZDpyZ2JhKHZhcigtLWN5KSwuMTYpO2JvcmRlci1jb2xvcjpyZ2JhKHZhcigtLWN5KSwu
NSl9Ci8qINGB0LLQvtC00LrQsCDQuCDRgdC70YPQttCx0YsgKi8KYm9keVtkYXRhLXBhZ2U9aG9tZV0gc2VjdGlvbi5jYXJkW2FyaWEtbGFiZWw90KHQstC+0LTQutCwXXtwYWRkaW5nOjEwcHggMThweDtib3JkZXItcmFkaXVzOjE2cHh9CmJvZHlbZGF0YS1wYWdl
PWhvbWVdIC5zdW17Z2FwOjEycHh9CmJvZHlbZGF0YS1wYWdlPWhvbWVdICNzdW1UZXh0e2ZvbnQtc2l6ZToxMnB4IWltcG9ydGFudDtsZXR0ZXItc3BhY2luZzouMWVtIWltcG9ydGFudH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmdyaWR7Z2FwOjEycHh9CmJvZHlb
ZGF0YS1wYWdlPWhvbWVdIC5jYXJkLnN2Y3twYWRkaW5nOjE2cHggMThweCAxNHB4O21pbi1oZWlnaHQ6MH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLnN2Yy1oe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjlweH0KYm9keVtkYXRhLXBhZ2U9aG9t
ZV0gLnN2Yy1oIGJ7Zm9udDo2MDAgMTRweCB2YXIoLS1ib2R5LGluaGVyaXQpO2xldHRlci1zcGFjaW5nOi4wMmVtO3RleHQtdHJhbnNmb3JtOm5vbmV9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5zdmMtaCAubXN7bWFyZ2luLWxlZnQ6YXV0bztmb250LXNpemU6MTBw
eDtjb2xvcjp2YXIoLS1tdTIsIzljODI3OSl9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5zdmMtc3Vie2ZvbnQtc2l6ZToxMXB4O21hcmdpbjoycHggMCA4cHh9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5saW5lcyBsaXtmb250LXNpemU6MTIuNXB4fQpib2R5W2RhdGEt
cGFnZT1ob21lXSAuc3ZjLXN0e21hcmdpbi10b3A6MTBweDtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMTZlbX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmNhcmQ+aDIsYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmNhcmQgLmgye2ZvbnQtc2l6ZToxMHB4O2xl
dHRlci1zcGFjaW5nOi4yNGVtO21hcmdpbi1ib3R0b206MTBweH0KLyog0LzQvtCx0LjQu9GM0L3QsNGPOiAzOTAgKi8KQG1lZGlhIChtYXgtd2lkdGg6ODYwcHgpe2JvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1oZXJve2dyaWQtdGVtcGxhdGUtY29sdW1uczptaW5t
YXgoMCwxZnIpfWJvZHlbZGF0YS1wYWdlPWhvbWVdIC5jYXJkLmM0e2Rpc3BsYXk6bm9uZX1ib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtcWF7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCg0LG1pbm1heCgwLDFmcikpfWJvZHlbZGF0YS1wYWdlPWhvbWVdIC5o
eC1xYSBhOm50aC1jaGlsZChuKzkpe2Rpc3BsYXk6bm9uZX1ib2R5W2RhdGEtcGFnZT1ob21lXSAjbnhtUGlsbHtib3R0b206Y2FsYyh2YXIoLS1kb2NrLWgsMHB4KSArIDZweCkhaW1wb3J0YW50O3RvcDphdXRvIWltcG9ydGFudH1ib2R5W2RhdGEtcGFnZT1ob21l
XSAucGggLnNlZ3t3aWR0aDphdXRvfWJvZHlbZGF0YS1wYWdlPWhvbWVdIC5waCAuYWN0c3ttYXJnaW4tbGVmdDphdXRvfX0KQG1lZGlhIChtYXgtd2lkdGg6NTYwcHgpewogYm9keVtkYXRhLXBhZ2U9aG9tZV0gLndyYXB7d2lkdGg6Y2FsYygxMDAlIC0gMjBweCk7
bWF4LXdpZHRoOmNhbGMoMTAwdncgLSAyMHB4KTtnYXA6MTBweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1nbGFzcyxib2R5W2RhdGEtcGFnZT1ob21lXSAuY2FyZHttYXgtd2lkdGg6MTAwJTtvdmVyZmxvdzpoaWRkZW59CiBib2R5W2RhdGEtcGFnZT1ob21l
XSAuaHgtaGl7cGFkZGluZzoxOHB4IDE2cHggMTZweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1oe2ZvbnQtc2l6ZToyNnB4O2xldHRlci1zcGFjaW5nOi4xZW19CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtc3Vie21hcmdpbi1ib3R0b206MTRweDtmb250
LXNpemU6MTNweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2t7bWluLWhlaWdodDo1NHB4O3BhZGRpbmctbGVmdDo0NHB4O2JvcmRlci1yYWRpdXM6MTdweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2s6OmJlZm9yZXtsZWZ0OjE1cHh9Ym9keVtk
YXRhLXBhZ2U9aG9tZV0gLmh4LWFzazo6YWZ0ZXJ7bGVmdDoyOHB4fQogYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWFzayBpbnB1dHtmb250LXNpemU6MTZweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2sgYnV0dG9ue3BhZGRpbmc6MCAxNHB4O21pbi1o
ZWlnaHQ6NDRweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2sgYnV0dG9uLmFsdHtkaXNwbGF5Om5vbmV9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrIGJ1dHRvbltkYXRhLW09YXNrXXtmb250LXNpemU6MDt3aWR0aDo0NHB4O3BhZGRpbmc6MDti
b3JkZXItcmFkaXVzOjUwJTtmbGV4Om5vbmV9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrIGJ1dHRvbltkYXRhLW09YXNrXTo6YmVmb3Jle2NvbnRlbnQ6J1wyMTkyJztmb250LXNpemU6MjBweDtjb2xvcjojZmZmfQogYm9keVtkYXRhLXBhZ2U9aG9tZV0g
Lmh4LXFhe2dhcDo4cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtcWEgYXttaW4taGVpZ2h0Ojg4cHg7Ym9yZGVyLXJhZGl1czoyMHB4O2ZvbnQtc2l6ZToxMC41cHg7cGFkZGluZzoxMHB4IDJweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1xYSBhIHNs
LWljb257d2lkdGg6NDRweDtoZWlnaHQ6NDRweDtmb250LXNpemU6MjNweDtib3JkZXItcmFkaXVzOjE0cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtZXZ7cGFkZGluZzoxNnB4fQp9CkBtZWRpYSAobWluLXdpZHRoOjg2MXB4KXtib2R5W2RhdGEtcGFnZT1o
b21lXSAuaHgtcWF7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCg2LG1pbm1heCgwLDFmcikpfWJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1xYSBhe21pbi1oZWlnaHQ6MTA0cHh9fQo=
S1EOF
echo OK nox-home-v.css $(wc -c <nox-home-v.css)
cd /workspace/nox/web/site
sed -i 's#nox-home-v.css?v=[0-9]*#nox-home-v.css?v='$(date +%s)'#' index.html
mkdir -p /workspace/nox/tools
cat > /workspace/nox/tools/s1_shot.py <<'S1PY'
import base64,subprocess,sys,json,time
from playwright.sync_api import sync_playwright
# usage: s1_shot.py page label [send] [vp=pc,4k,mob]
page=sys.argv[1]; L=sys.argv[2]; opts=sys.argv[3:]
send='send' in opts
vps=[('pc',1440,900,0),('4k',3840,2160,0),('mob',390,844,1)]
sel=[o.split('=')[1] for o in opts if o.startswith('vp=')]
if sel: vps=[v for v in vps if v[0] in sel[0].split(',')]
def out(tag,png,w):
    j='/tmp/s_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','11',j])
    for suf,q in (('',11),('b',16)):
        subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v',str(q),j])
        b=base64.b64encode(open(j,'rb').read()).decode()
        print('B64_%s%s_BEGIN'%(tag,suf))
        for i in range(0,len(b),900): print(b[i:i+900])
        print('B64_%s%s_END'%(tag,suf))
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--ignore-gpu-blocklist'])
    for name,w,h,mob in vps:
        ctx=b.new_context(viewport={'width':w,'height':h},has_touch=bool(mob),is_mobile=bool(mob))
        pg=ctx.new_page(); errs=[]; bad=[]
        pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        pg.on('response',lambda r:bad.append('%d %s'%(r.status,r.url[-90:])) if r.status>=400 else None)
        pg.on('requestfailed',lambda r:bad.append('FAIL '+r.url[-90:]))
        if 'seed' in opts:
            import json as J
            md="Вот пример ответа.\n\n- пункт один\n- пункт два\n\n```python\nprint('привет')\n```\n\nФормула: $E=mc^2$\n\n$$\\int_0^1 x^2dx=\\frac13$$\n\n```mermaid\ngraph LR; A[Вопрос]-->B[Ядро]; B-->C[Ответ]\n```"
            th=[{'id':'seed-1','title':'Проверка разметки','ts':1795576425326,'msgs':[{'role':'user','content':'Покажи пример кода, формулу и схему','ts':1795576431803,'att':[]},{'role':'assistant','content':md,'ts':1795576431822,'via':'УРОВЕНЬ: НОКС'},{'role':'user','content':'Спасибо, а теперь коротко','ts':1795576531803,'att':[]},{'role':'assistant','content':'Готово: код, формула и схема выше.','ts':1795576531822}],'srv':False}]
            ctx.add_init_script("try{localStorage.setItem('nox.wow.threads',%s)}catch(e){}"%J.dumps(J.dumps(th)))
        pg.goto('http://localhost:8091/web/'+page,wait_until='load'); pg.wait_for_timeout(6000)
        if send and name=='pc':
            try:
                pg.evaluate("document.querySelector('#modes [data-m=fast]').click()"); pg.fill('#input','привет, ответь коротко одной строкой'); pg.keyboard.press('Enter')
                for i in range(30):
                    pg.wait_for_timeout(2000)
                    t=pg.evaluate("(()=>{const a=[...document.querySelectorAll('#msgs .m.a .txt')].pop();return a?a.innerText:''})()")
                    if t and 'ОЖИДАНИЕ' not in t and not pg.evaluate("document.body.classList.contains('nox-busy')"): break
                print('REPLY',json.dumps(t,ensure_ascii=False)[:300])
                print('LSTHREADS',(pg.evaluate("localStorage.getItem('nox.wow.threads')") or '')[:700])
                print('BUBBLE_ERR',pg.evaluate("!!document.querySelector('.bubble.err')"))
            except Exception as e: print('SENDERR',e)
        if send and name=='pc':
            try: pg.hover('#msgs .m.a .bubble'); pg.wait_for_timeout(500)
            except Exception as e: print('HOVERERR',str(e)[:80])
        if name=='pc' and 'qhelp' in opts:
            print('FIXED',pg.evaluate("[...document.querySelectorAll('body *')].filter(e=>{const c=getComputedStyle(e);const r=e.getBoundingClientRect();return c.position=='fixed'&&r.width<70&&r.width>20&&r.left<80&&r.top>600}).map(e=>e.outerHTML.slice(0,200)).join('\\n')"))
        pg.screenshot(path='/tmp/s.png')
        out(L+'_'+name,'/tmp/s.png',1100 if w>1500 else w)
        if 'slash' in opts and name=='pc':
            pg.fill('#input','/'); pg.wait_for_timeout(600); pg.screenshot(path='/tmp/s2.png'); out(L+'_slash','/tmp/s2.png',1100)
        print('ERRS',name,errs[:4]); print('BAD',name,bad[:12])
        ctx.close()
    b.close()

S1PY
cd /tmp
/workspace/nox/venv/bin/python /workspace/nox/tools/s1_shot.py index.html hm6 vp=pc,4k 2>&1 | cut -c1-900
