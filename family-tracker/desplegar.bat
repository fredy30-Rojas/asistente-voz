echo Subiendo archivos del servidor...
gcloud compute scp "server/web_server_modified.py" claude-bot-vm:/tmp/web_server_new.py --zone=us-central1-a
gcloud compute scp "server/dashboard.html" claude-bot-vm:/tmp/dashboard.html --zone=us-central1-a

echo Desplegando en la VM...
gcloud compute ssh claude-bot-vm --zone=us-central1-a --command="sudo cp /tmp/web_server_new.py /home/fredy/claude-bot/web_server.py && sudo cp /tmp/dashboard.html /home/fredy/claude-bot/dashboard.html && sudo systemctl restart claude-web && echo 'Servidor reiniciado'"

echo Probando GPS...
gcloud compute ssh claude-bot-vm --zone=us-central1-a --command="curl -s -X POST https://34-173-169-64.nip.io/api/gps -H 'Content-Type: application/json' -d '{\"name\":\"test\",\"lat\":41.49,\"lon\":2.03}'"

echo Listo. Abre https://34-173-169-64.nip.io/dashboard para ver el mapa.
