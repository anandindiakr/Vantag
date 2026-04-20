// pm2 ecosystem — manages backend + frontend as persistent background services
// Start:   pm2 start ecosystem.config.js
// Stop:    pm2 stop all
// Restart: pm2 restart all
// Logs:    pm2 logs
// Status:  pm2 status

module.exports = {
  apps: [
    {
      name: 'vantag-backend',
      script: 'python',
      args: '-m uvicorn backend.api.main:app --host 0.0.0.0 --port 8800',
      cwd: 'D:\\AI Algo\\Collaterals\\Profiles\\Retail Nazar\\vantag',
      interpreter: 'none',
      env: {
        PYTHONPATH:        'D:\\AI Algo\\Collaterals\\Profiles\\Retail Nazar\\vantag',
        VANTAG_SMTP_HOST:  'smtp.gmail.com',
        VANTAG_SMTP_PORT:  '587',
        VANTAG_SMTP_USER:  'anandindiakr@gmail.com',
        VANTAG_SMTP_PASS:  'syvwqwezqjsirrnj',
        VANTAG_EMAIL_FROM: 'Vantag <anandindiakr@gmail.com>',
      },
      autorestart:   true,
      watch:         false,
      max_restarts:  10,
      restart_delay: 3000,
      out_file:   'D:\\AI Algo\\Collaterals\\Profiles\\Retail Nazar\\vantag\\logs\\backend-out.log',
      error_file: 'D:\\AI Algo\\Collaterals\\Profiles\\Retail Nazar\\vantag\\logs\\backend-err.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'vantag-frontend',
      // Windows: use cmd /c so npx.cmd resolves correctly
      script: 'cmd',
      args: '/c npx vite --port 3000 --host',
      cwd: 'D:\\AI Algo\\Collaterals\\Profiles\\Retail Nazar\\vantag\\frontend\\web',
      interpreter: 'none',
      autorestart:   true,
      watch:         false,
      max_restarts:  10,
      restart_delay: 2000,
      out_file:   'D:\\AI Algo\\Collaterals\\Profiles\\Retail Nazar\\vantag\\logs\\frontend-out.log',
      error_file: 'D:\\AI Algo\\Collaterals\\Profiles\\Retail Nazar\\vantag\\logs\\frontend-err.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
};
