# Configuración de la pestaña Corte temporal

Todo lo que se ajusta en esta pestaña está en esta carpeta.

| Archivo | Para qué sirve |
|---|---|
| `capas_nc.json` | Capas NetCDF que el conversor (`_2_CreaNC`) debe crear para esta pestaña. Formato `variable_nivelhPa` (`t_850hPa`, `r_700hPa`, `u_500hPa`, `v_500hPa`). `t` = temperatura, `r` = humedad relativa, `u`/`v` = componentes del viento. **Es la única lista de niveles:** la pantalla muestra los niveles que estén en `true` aquí. |
| `variables.json` | Qué se muestra: cómo se guarda cada capa (`capas`: unidad, factor y desplazamiento) y las variables y vistas de la pantalla (`variables`: campo, unidades, rango y paso de colores, paleta, contornos resaltados, barbas, `centro` de la paleta). |
| `puntos.json` | Puntos de esta pestaña (`área → punto → lat/lon`). Se copió de `_0_Visor/Puntos.json` y se puede editar sin afectar a las Tablas. |
| `almacenamiento.json` | `publicar_nc_en_git`: `false` (recomendado) sube a GitHub solo el respaldo compacto; `true` sube también las 76 capas de cada ciclo. |

## Cómo se conecta con el resto

1. `_2_CreaNC/__Configuracion_NC.toml` lista `capas_nc.json` en `selecciones_adicionales`: sus capas activas se **suman** a `seleccion_nc.json`.
2. El workflow ejecuta `python _0_Visor/archivar_corte.py` y guarda los perfiles de todos los puntos en `___Data/___Historico_Corte/AAAAMMDD_HHZ.parquet` (respaldo: no se borra solo).
3. La pantalla lee las capas NetCDF si están en `___Data/___NC` (siempre con los puntos actuales) y, si no, el respaldo.

## Tareas habituales

- **Cambiar o agregar puntos:** edita `puntos.json`. Con los NetCDF de esos ciclos en tu PC, rehaz los respaldos con
  `python _0_Visor/archivar_corte.py --todos`. Un punto debe quedar dentro del área descargada
  (`norte/sur/oeste/este` de `__Configuracion_Fnnn.toml`); si no, se omite y se avisa en el registro.
- **Quitar o agregar niveles:** cambia `true`/`false` en `capas_nc.json` (el nivel debe existir en `_2_CreaNC/__Variables_NC.toml`).
  Menos niveles = menos peso por ciclo.
- **Cambiar colores o escalas:** edita `paleta`, `min`, `max`, `paso` o `centro` en `variables.json`. Las paletas son nombres de matplotlib (`YlGnBu`, `RdYlBu_r`…).
- **Agregar una unidad al viento:** añade un bloque en `unidades` con `factor` desde m/s.
