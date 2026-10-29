# 🩺 Salud y alarma — versión fácil

> Todo el detalle: [manual completo](../SALUD.md)

## ¿Para qué sirve?
Para saber **si la Academia está sana** y **cómo estudias hoy**, y poder comprobar después si algo mejora.

## El botón 🩺
- **Estado del equipo** (solo el administrador): problemas con color (🔴 alta, 🟠 media), tareas en cola, si la IA responde, GPU, disco y la rutina diaria.
  Si no hay problemas dice «✅ Sin problemas».
- **Tu línea base** (solo tú): una foto de cómo estudias hoy. Cada número dice de dónde sale. Con el tiempo verás cuánto cambió.

## La alarma (vigía)
Es un programa **aparte** que mira cada 2 minutos. Si la Academia se cae, te avisa **en menos de 5 minutos** por el canal que elijas (por ejemplo, Telegram).
Avisa **una vez** de cada problema, te lo recuerda cada 6 horas si es grave y te dice cuando se arregla.

- Probar el canal: `python3 app/vigia.py --probar`
- Vas a apagar la Academia a propósito: `python3 app/vigia.py --pausar` (se quita sola cuando vuelva).

## Si reinicias la Academia
Lo que estaba en la cola **se recupera solo**. Si algo que estabas esperando (una pregunta al tutor, por ejemplo) no se puede recuperar, 🩺 te lo dice y solo tienes que
pedirlo otra vez.
