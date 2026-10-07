// Configurazione PM2: bot e sito in due processi separati, cosi' se uno
// cade l'altro resta su e PM2 riavvia solo quello. Condividono la cache
// SQLite (in modalita' WAL): il bot la scrive, il sito la legge.
//
// Primo deploy (o migrazione dal vecchio processo unico):
//   pm2 delete cinema-bologna-bot; pm2 start ecosystem.config.js && pm2 save
// Aggiornamenti successivi:
//   pm2 restart ecosystem.config.js
const common = {
  interpreter: "./.venv/bin/python",
  cwd: __dirname,
  autorestart: true,
  max_restarts: 10,
  restart_delay: 5000,
  kill_timeout: 8000,
  time: true,
  env: {
    PYTHONUNBUFFERED: "1",
  },
};

module.exports = {
  apps: [
    {
      ...common,
      name: "cinema-bologna-bot",
      script: "main.py",
      args: "--bot",
      out_file: "logs/pm2-bot-out.log",
      error_file: "logs/pm2-bot-err.log",
    },
    {
      ...common,
      name: "cinema-bologna-web",
      script: "main.py",
      args: "--web",
      out_file: "logs/pm2-web-out.log",
      error_file: "logs/pm2-web-err.log",
    },
  ],
};
