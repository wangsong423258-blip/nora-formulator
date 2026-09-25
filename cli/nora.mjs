#!/usr/bin/env node
import { pathToFileURL } from 'node:url';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { readFile, lstat, writeFile, rename, rm } from 'node:fs/promises';
import { readSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { NoraClient } from '../sdk/client.mjs';
import { installBundle, runtimeCommand, inspectBundle, updateBundle, activate, uninstallBundle } from './install.mjs';

const usage = 'Usage: nora version | status | install --bundle DIR | start | stop | update --bundle DIR | uninstall | enroll [--provider NAME] | license import FILE [--grant FILE] [--home DIR]';

async function invoke(home, args, unlock) {
  const executable = await runtimeCommand(home);
  return new Promise(resolveExit => {
    const child = spawn(executable, [...args, '--home', resolve(home)], { stdio: unlock ? ['pipe', 'inherit', 'inherit'] : 'inherit', shell: false });
    if (unlock) { child.stdin.on('error', () => {}); child.stdin.end(unlock); }
    child.once('error', () => resolveExit(1));
    child.once('exit', code => resolveExit(code ?? 1));
  });
}

export async function main(args, { env = process.env, out = console.log, err = console.error, makeClient = options => new NoraClient(options) } = {}) {
  if (args.length === 1 && ['--help', '-h'].includes(args[0])) { out(usage); return 0; }
  const command = args[0];
  const rest = args.slice(1);
  let home = env.NORA_HOME || join(homedir(), '.nora');
  if (rest.includes('--home')) {
    const i = rest.indexOf('--home');
    if (!rest[i + 1]) { err(usage); return 2; }
    home = resolve(rest[i + 1]); rest.splice(i, 2);
  }
  try {
    if (command === 'uninstall' && rest.length === 0) {
      await uninstallBundle(home); out('Nora Runtime and local authorization removed.'); return 0;
    }
    if (command === 'install' && rest.length === 2 && rest[0] === '--bundle') {
      await installBundle(rest[1], home); out('Nora Runtime installed.'); return 0;
    }
    if (['start', 'stop', 'enroll'].includes(command)) {
      const nativeArgs = [command];
      for (let i = 0; i < rest.length; i += 2) {
        if (!['--provider', '--unlock-fd'].includes(rest[i]) || !rest[i + 1] || command === 'stop') throw new Error();
        nativeArgs.push(rest[i], rest[i + 1]);
      }
      return await invoke(home, nativeArgs);
    }
    if (command === 'license' && rest[0] === 'import' && rest[1]) {
      const nativeArgs = ['license', 'import', resolve(rest[1])];
      for (let i = 2; i < rest.length; i += 2) {
        if (!['--grant', '--unlock-fd'].includes(rest[i]) || !rest[i + 1]) throw new Error();
        nativeArgs.push(rest[i], rest[i] === '--grant' ? resolve(rest[i + 1]) : rest[i + 1]);
      }
      return await invoke(home, nativeArgs);
    }
    if (command === 'update' && rest.length >= 2 && rest.length % 2 === 0 && rest[0] === '--bundle') {
      const options = new Map();
      for (let i = 0; i < rest.length; i += 2) {
        if (!['--bundle', '--unlock-fd', '--license', '--grant'].includes(rest[i]) || options.has(rest[i]) || !rest[i + 1]) throw new Error();
        options.set(rest[i], rest[i + 1]);
      }
      if (options.has('--license') !== options.has('--grant')) throw new Error();
      let unlock;
      if (options.has('--unlock-fd')) {
        const fd = options.get('--unlock-fd');
        if (!/^\d+$/.test(fd)) throw new Error();
        unlock = Buffer.alloc(1025);
        let count = 0, size;
        while (count < unlock.length && (size = readSync(Number(fd), unlock, count, unlock.length - count, null))) count += size;
        if (!count || count > 1024) { unlock.fill(0); throw new Error(); }
        unlock = unlock.subarray(0, count);
      }
      try {
      await inspectBundle(rest[1]);
      let running = false;
      try {
        const file = join(home, 'connection.json');
        const stat = await lstat(file);
        if (!stat.isFile() || stat.isSymbolicLink() || (process.platform !== 'win32' && (stat.mode & 0o077))) throw new Error();
        const c = JSON.parse(await readFile(file, 'utf8'));
        await makeClient(c).runtimeStatus(); running = true;
      } catch {}
      let update, entitlement;
      const active = join(home, 'entitlements', 'active.json');
      try {
        const stat = await lstat(active);
        if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 16384) throw new Error();
        entitlement = await readFile(active);
      } catch (error) { if (error.code !== 'ENOENT') throw error; }
      if (running && await invoke(home, ['stop']) !== 0) throw new Error();
      try {
        update = await updateBundle(rest[1], home);
        if (options.has('--license')) {
          const args = ['license', 'import', resolve(options.get('--license')), '--grant', resolve(options.get('--grant'))];
          if (unlock) args.push('--unlock-fd', '0');
          if (await invoke(home, args, unlock) !== 0) throw new Error();
        }
        if (await invoke(home, ['check']) !== 0) throw new Error();
        if (running && await invoke(home, unlock ? ['start', '--unlock-fd', '0'] : ['start'], unlock) !== 0) throw new Error();
      } catch (error) {
        if (update) {
          await activate(home, update.previous);
          if (options.has('--license')) {
            if (entitlement) {
              const pending = active + '.rollback';
              await writeFile(pending, entitlement, { flag: 'wx', mode: 0o600 });
              await rename(pending, active);
            } else await rm(active, { force: true });
          }
        }
        if (running) await invoke(home, unlock ? ['start', '--unlock-fd', '0'] : ['start'], unlock);
        throw error;
      }
      out('Nora Runtime updated. Previous signed release retained for recovery.'); return 0;
      } finally { if (unlock) unlock.fill(0); }
    }
    if (['version', 'status'].includes(command) && rest.length === 0) {
      let baseUrl = env.NORA_API_URL, token = env.NORA_API_TOKEN;
      if (!baseUrl || !token) {
        const file = env.NORA_CONNECTION_FILE || join(home, 'connection.json');
        let stat;
        try { stat = await lstat(file); }
        catch { err('Start Nora Runtime or configure a local connection file.'); return 2; }
        if (!stat.isFile() || stat.isSymbolicLink() || (process.platform !== 'win32' && (stat.mode & 0o077))) throw new Error();
        ({ baseUrl, token } = JSON.parse(await readFile(file, 'utf8')));
      }
      const client = makeClient({ baseUrl, token });
      out(JSON.stringify(command === 'version' ? (await client.version()).metadata : await client.runtimeStatus()));
      return 0;
    }
    err(usage); return 2;
  } catch { err('Nora operation failed. Check local configuration, signed distribution and access.'); return 1; }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) process.exitCode = await main(process.argv.slice(2));
