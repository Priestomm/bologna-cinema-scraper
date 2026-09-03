// Configurazione PM2 per avviare il bot come daemon.
// Uso: pm2 start ecosystem.config.js && pm2 save && pm2 startup
module.exports = {
  apps: [
    {
      name: "cinema-bologna-bot",
      script: "main.py",
      interpreter: "./.venv/bin/python",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      kill_timeout: 8000,
      out_file: "logs/pm2-out.log",
      error_file: "logs/pm2-err.log",
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
