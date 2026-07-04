import pyperclip,time,asyncio,edge_tts,os
ultimo=""
async def hablar(t):
 c=edge_tts.Communicate(t,voice="es-ES-AlvaroNeural")
 await c.save("out.mp3")
 os.system("start out.mp3")
while True:
 t=pyperclip.paste().strip()
 if t!=ultimo and len(t)>5:
  ultimo=t
  asyncio.run(hablar(t))
 time.sleep(1.5)
