const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

// Search candidates for python executable in root or local virtualenvs
const candidates = [
  path.resolve(__dirname, '../../..', '.venv', 'Scripts', 'python.exe'),
  path.resolve(__dirname, '../../..', '.venv', 'bin', 'python'),
  path.resolve(__dirname, '..', '.venv', 'Scripts', 'python.exe'),
  path.resolve(__dirname, '..', '.venv', 'bin', 'python'),
];

let pythonExe = 'python';
for (const cand of candidates) {
  if (fs.existsSync(cand)) {
    pythonExe = cand;
    break;
  }
}

const args = process.argv.slice(2);
const child = spawn(pythonExe, args, {
  stdio: 'inherit',
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 0);
  }
});
