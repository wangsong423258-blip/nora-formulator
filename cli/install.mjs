import { createHash, createPublicKey, verify, randomUUID } from 'node:crypto';
import { lstat, readFile, mkdir, writeFile, rename, readdir, rm } from 'node:fs/promises';
import { resolve, join, dirname, sep } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { releaseKeys, releaseChannel } from '../sdk/release-trust.mjs';
import { homedir } from 'node:os';

function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  return JSON.stringify(value);
}

async function protectHome(home) {
  if (process.platform !== 'win32') return;
  const script = "$ErrorActionPreference='Stop'; $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User; $acl=New-Object System.Security.AccessControl.DirectorySecurity; $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false); $rule=New-Object System.Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'); $acl.AddAccessRule($rule); Set-Acl -LiteralPath $env:NORA_INSTALL_HOME -AclObject $acl";
  await promisify(execFile)('powershell.exe', ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { env: { ...process.env, NORA_INSTALL_HOME: home }, windowsHide: true });
}

async function regular(path) {
  const s = await lstat(path);
  if (!s.isFile() || s.isSymbolicLink() || s.nlink !== 1) throw new Error('BUNDLE_FILE_INVALID');
  return s;
}

async function noLinkedParents(path) {
  let current = resolve(path);
  while (true) {
    try { if ((await lstat(current)).isSymbolicLink()) throw new Error('LINKED_PATH'); }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }
}

export async function inspectBundle(bundle, { keys = releaseKeys, platform = process.platform, arch = process.arch, channel = releaseChannel } = {}) {
  bundle = resolve(bundle);
  await noLinkedParents(bundle);
  const manifestPath = join(bundle, 'release.signed.json');
  if ((await regular(manifestPath)).size > 1048576) throw new Error('MANIFEST_TOO_LARGE');
  const doc = JSON.parse(await readFile(manifestPath, 'utf8'));
  if (Object.keys(doc).sort().join(',') !== 'format,key_id,payload,purpose,signature' ||
      doc.format !== 'nora-signed-v1' || doc.purpose !== 'release' || !Object.hasOwn(keys, doc.key_id)) throw new Error('UNTRUSTED_RELEASE');
  const publicKey = createPublicKey({ key: Buffer.concat([
    Buffer.from('302a300506032b6570032100', 'hex'), Buffer.from(keys[doc.key_id], 'base64'),
  ]), format: 'der', type: 'spki' });
  const bytes = Buffer.concat([Buffer.from('Nora.signed.v1\0'), Buffer.from(canonical({ purpose: doc.purpose, key_id: doc.key_id, payload: doc.payload }))]);
  if (!verify(null, bytes, publicKey, Buffer.from(doc.signature, 'base64'))) throw new Error('RELEASE_SIGNATURE_INVALID');
  const p = doc.payload;
  const entry = platform === 'win32' ? 'nora-runtime.exe' : 'nora-runtime';
  if (p.channel !== channel || p.product !== 'Nora' || p.native !== true || p.platform !== platform ||
      p.arch !== arch || p.entrypoint !== entry || !/^\d+\.\d+\.\d+$/.test(p.version)) throw new Error('RELEASE_INCOMPATIBLE');
  if (p.schema_version === 2) return inspectV2(bundle, p);
  if (!Array.isArray(p.files) || p.files.length < 4 || p.files.length > 256) throw new Error('RELEASE_FILES_INVALID');
  const names = new Set();
  let size = 0;
  for (const f of p.files) {
    if (typeof f.path !== 'string' || names.has(f.path) ||
        !/^(?:nora-runtime(?:\.exe)?|[A-Za-z0-9_-]+\.(?:dll|dylib|so)|nora-data-[A-Za-z0-9_.-]+\.pack|community\.license\.json|data-key\.sealed|LICENSE\.runtime\.txt)$/.test(f.path) ||
        !/^[a-f0-9]{64}$/.test(f.sha256)) throw new Error('RELEASE_FILES_INVALID');
    names.add(f.path);
    const file = join(bundle, f.path);
    const stat = await regular(file);
    size += stat.size;
    if (size > 1073741824) throw new Error('BUNDLE_TOO_LARGE');
    const data = await readFile(file);
    if (createHash('sha256').update(data).digest('hex') !== f.sha256) throw new Error('RELEASE_INTEGRITY_INVALID');
  }
  if (!names.has(entry) || !names.has('community.license.json') || !names.has('data-key.sealed') ||
      !names.has('LICENSE.runtime.txt') || ![...names].some(x => x.endsWith('.pack'))) throw new Error('RELEASE_INCOMPLETE');
  if ((await readdir(bundle)).sort().join('\0') !== [...names, 'release.signed.json'].sort().join('\0')) throw new Error('UNMANIFESTED_BUNDLE_FILE');
  return p;
}

export async function installBundle(bundle, home, options = {}) {
  const p = await inspectBundle(bundle, options);
  if (p.schema_version === 2) return installV2(bundle, home, p, options);
  home = resolve(home);
  await noLinkedParents(home);
  await mkdir(home, { recursive: false, mode: 0o700 });
  await protectHome(home);
  const slot = join(home, 'runtime');
  await mkdir(slot, { mode: 0o700 });
  for (const f of p.files) {
    const data = await readFile(join(resolve(bundle), f.path));
    if (createHash('sha256').update(data).digest('hex') !== f.sha256) throw new Error('BUNDLE_CHANGED');
    await writeFile(join(slot, f.path), data, { flag: 'wx', mode: f.path === p.entrypoint ? 0o700 : 0o600 });
  }
  await writeFile(join(slot, 'release.signed.json'), await readFile(join(resolve(bundle), 'release.signed.json')), { flag: 'wx', mode: 0o600 });
  await inspectBundle(slot, options);
  await writeFile(join(home, 'installation.json.pending'), JSON.stringify({ entrypoint: p.entrypoint, version: p.version }), { flag: 'wx', mode: 0o600 });
  await rename(join(home, 'installation.json.pending'), join(home, 'installation.json'));
  return { version: p.version };
}

export async function runtimeCommand(home) {
  home = resolve(home);
  await noLinkedParents(home);
  const pointer = await installation(home);
  const slot = pointer.schema_version === 2 ? join(home, 'releases', pointer.release) : join(home, 'runtime');
  const p = await inspectBundle(slot);
  const command = join(slot, p.entrypoint);
  if (!command.startsWith(home + sep)) throw new Error('INVALID_RUNTIME_PATH');
  return command;
}

// Remove only an authenticated, dedicated installation. Unknown files, linked
// paths, an update in progress, or failed stop/key removal leave it intact.
export async function uninstallBundle(home, options = {}) {
  home = resolve(home);
  if (home === dirname(home) || home === resolve(homedir())) throw new Error('UNINSTALL_PATH_INVALID');
  await noLinkedParents(home);
  const stat = await lstat(home);
  if (!stat.isDirectory() || (process.getuid && stat.uid !== process.getuid())) throw new Error('UNINSTALL_OWNER_INVALID');
  const allowed = new Set(['installation.json', 'releases', 'device', 'entitlements', 'connection.json', 'stop.request']);
  if ((await readdir(home)).some(name => !allowed.has(name))) throw new Error('UNINSTALL_UNKNOWN_FILES');
  const pointer = await installation(home);
  if (pointer.schema_version !== 2) throw new Error('UNINSTALL_FORMAT_UNSUPPORTED');
  const slots = await readdir(join(home, 'releases'));
  if (!slots.includes(pointer.release) || slots.some(name => !/^[a-f0-9]{64}$/.test(name))) throw new Error('UNINSTALL_RELEASE_INVALID');
  let activeRelease;
  for (const slot of slots) {
    const verified = await inspectBundle(join(home, 'releases', slot), options);
    if (slot === pointer.release) activeRelease = verified;
  }
  async function safeTree(path) {
    const s = await lstat(path);
    if (s.isSymbolicLink() || (!s.isDirectory() && !s.isFile()) || (s.isFile() && s.nlink !== 1)) throw new Error('UNINSTALL_LINKED_FILE');
    if (s.isDirectory()) for (const name of await readdir(path)) await safeTree(join(path, name));
  }
  await safeTree(home);
  let device;
  try { device = JSON.parse(await readFile(join(home, 'device', 'enrollment.json'), 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (device) {
    const key = Buffer.from(device.public_key || '', 'base64');
    if (key.length !== 32 || createHash('sha256').update(key).digest('hex') !== device.device_id ||
        !['macos-keychain-v1', 'passphrase-scrypt-v1'].includes(device.provider)) throw new Error('UNINSTALL_DEVICE_INVALID');
  }
  const lock = join(home, '.update-lock');
  await writeFile(lock, '', { flag: 'wx', mode: 0o600 });
  try {
    try {
      await lstat(join(home, 'connection.json'));
      await promisify(execFile)(join(home, 'releases', pointer.release, activeRelease.entrypoint), ['stop', '--home', home], { timeout: 30000 });
      try { await lstat(join(home, 'connection.json')); throw new Error('UNINSTALL_RUNTIME_STILL_RUNNING'); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (device?.provider === 'macos-keychain-v1') {
      if (process.platform !== 'darwin') throw new Error('UNINSTALL_PLATFORM_INVALID');
      try { await promisify(execFile)('/usr/bin/security', ['delete-generic-password', '-s', 'com.palecho.nora.device.v1', '-a', device.device_id]); }
      catch (error) { if (error.code !== 44) throw new Error('UNINSTALL_KEYCHAIN_FAILED'); }
    }
    await rm(home, { recursive: true });
    return { uninstalled: true };
  } finally { await rm(lock, { force: true }); }
}

async function tree(root, prefix = '') {
  const paths = [];
  for (const name of await readdir(join(root, prefix))) {
    const rel = prefix ? prefix + '/' + name : name;
    if (!name || name === '.' || name === '..' || name.startsWith('.') || !/^[A-Za-z0-9_+.-]+$/.test(name)) throw new Error('RELEASE_PATH_INVALID');
    const s = await lstat(join(root, rel));
    if (s.isSymbolicLink()) throw new Error('LINKED_ARTIFACT');
    if (s.isDirectory()) paths.push(...await tree(root, rel));
    else { await regular(join(root, rel)); paths.push(rel); }
  }
  return paths;
}

function allowedAsset(path, entry, pack) {
  if (path === entry || path === pack) return true;
  if (path === 'licenses/community.license.json') return true;
  if (path.split('/').some(x => !x || x === '.' || x === '..' || x.startsWith('.'))) return false;
  if (/\.(?:so|dylib|dll|pyd)$/.test(path)) return true;
  if (/^[A-Za-z0-9_+./-]+\.npz$/.test(path)) return true;
  if (/^licenses\/[A-Za-z0-9_+./-]+\.(?:txt|md)$/.test(path)) return true;
  if (/^jsonschema_specifications\/schemas\/[A-Za-z0-9_+./-]+(?:\.json)?$/.test(path)) return true;
  if (/^[A-Za-z0-9_+.-]+\.dist-info\/(?:METADATA|WHEEL|INSTALLER|entry_points\.txt|top_level\.txt)$/.test(path)) return true;
  return false;
}

async function inspectV2(bundle, p) {
  if (p.api_version !== 'v1' || p.runtime_compatibility !== '1' || p.license_schema_version !== 1 ||
      typeof p.data_version !== 'string' || !/^nora-data-[A-Za-z0-9_.-]+\.pack$/.test(p.datapack)) throw new Error('VERSION_INCOMPATIBLE');
  if (!Array.isArray(p.files) || p.files.length < 3 || p.files.length > 4096) throw new Error('RELEASE_FILES_INVALID');
  const names = new Set(); let size = 0;
  for (const row of p.files) {
    if (typeof row.path !== 'string' || !/^[A-Za-z0-9_+./-]+$/.test(row.path) || names.has(row.path) ||
        !allowedAsset(row.path, p.entrypoint, p.datapack) || !/^[a-f0-9]{64}$/.test(row.sha256)) throw new Error('RELEASE_FILES_INVALID');
    names.add(row.path);
    const file = join(bundle, row.path); await noLinkedParents(file);
    const s = await regular(file); size += s.size;
    if (size > 1073741824) throw new Error('BUNDLE_TOO_LARGE');
    const bytes = await readFile(file);
    if (createHash('sha256').update(bytes).digest('hex') !== row.sha256) throw new Error('RELEASE_INTEGRITY_INVALID');
    if (row.path === p.entrypoint || /\.(?:so|dylib|dll|pyd)$/.test(row.path)) {
      const magic = bytes.subarray(0, 4).toString('hex');
      const native = p.platform === 'win32' ? bytes.subarray(0, 2).toString() === 'MZ' : p.platform === 'linux' ? magic === '7f454c46' : ['cffaedfe', 'feedfacf', 'cafebabe', 'cafebabf'].includes(magic);
      if (!native) throw new Error('NATIVE_ARTIFACT_INVALID');
    }
  }
  if (!names.has(p.entrypoint) || !names.has(p.datapack) || !names.has('licenses/LICENSE.runtime.txt')) throw new Error('RELEASE_INCOMPLETE');
  if ((await tree(bundle)).sort().join('\0') !== [...names, 'release.signed.json'].sort().join('\0')) throw new Error('UNMANIFESTED_BUNDLE_FILE');
  return p;
}

export async function installation(home) {
  await noLinkedParents(home);
  const file = join(home, 'installation.json');
  if ((await regular(file)).size > 16384) throw new Error('INSTALLATION_INVALID');
  const pointer = JSON.parse(await readFile(file, 'utf8'));
  if (pointer.schema_version === 2 && !/^[a-f0-9]{64}$/.test(pointer.release)) throw new Error('INSTALLATION_INVALID');
  return pointer;
}

async function stage(bundle, home, p, options) {
  const manifest = await readFile(join(resolve(bundle), 'release.signed.json'));
  const release = createHash('sha256').update(manifest).digest('hex');
  const root = join(home, 'releases'); await mkdir(root, { recursive: true, mode: 0o700 });
  const pending = join(root, '.pending-' + randomUUID()); await mkdir(pending, { mode: 0o700 });
  try {
    for (const row of p.files) {
      const bytes = await readFile(join(resolve(bundle), row.path));
      if (createHash('sha256').update(bytes).digest('hex') !== row.sha256) throw new Error('BUNDLE_CHANGED');
      const target = join(pending, row.path); await mkdir(dirname(target), { recursive: true, mode: 0o700 });
      await writeFile(target, bytes, { flag: 'wx', mode: row.path === p.entrypoint ? 0o700 : 0o600 });
    }
    await writeFile(join(pending, 'release.signed.json'), manifest, { flag: 'wx', mode: 0o600 });
    await inspectBundle(pending, options);
    const target = join(root, release);
    try { await lstat(target); throw new Error('RELEASE_ALREADY_INSTALLED'); }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
    await rename(pending, target);
    return { schema_version: 2, release, version: p.version, entrypoint: p.entrypoint };
  } finally { await rm(pending, { recursive: true, force: true }); }
}

export async function activate(home, pointer) {
  await noLinkedParents(home);
  const pending = join(home, '.installation-' + randomUUID());
  try {
    await writeFile(pending, JSON.stringify(pointer), { flag: 'wx', mode: 0o600 });
    await rename(pending, join(home, 'installation.json'));
  } finally { await rm(pending, { force: true }); }
}

async function installV2(bundle, home, p, options) {
  home = resolve(home); await noLinkedParents(home);
  await mkdir(home, { recursive: false, mode: 0o700 });
  try {
    await protectHome(home);
    const pointer = await stage(bundle, home, p, options);
    await activate(home, pointer); return { version: p.version };
  } catch (error) {
    await rm(home, { recursive: true, force: true }); throw error;
  }
}

export async function updateBundle(bundle, home, options = {}) {
  home = resolve(home); await noLinkedParents(home);
  const lock = join(home, '.update-lock');
  await writeFile(lock, 'updating', { flag: 'wx', mode: 0o600 });
  try {
    const before = await installation(home); const p = await inspectBundle(bundle, options);
    if (before.schema_version !== 2 || p.schema_version !== 2) throw new Error('UPDATE_FORMAT_INCOMPATIBLE');
    const old = before.version.split('.').map(Number), next = p.version.split('.').map(Number);
    let comparison = 0;
    for (let i = 0; i < 3 && comparison === 0; i++) comparison = Math.sign(next[i] - old[i]);
    if (comparison <= 0) throw new Error('UPDATE_MUST_ADVANCE_VERSION');
    const pointer = await stage(bundle, home, p, options);
    await activate(home, pointer);
    return { version: p.version, previous: before };
  } finally { await rm(lock, { force: true }); }
}
