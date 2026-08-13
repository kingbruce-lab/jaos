import {
  constants as cryptoConstants,
  createCipheriv,
  createDecipheriv,
  createHmac,
  publicEncrypt,
  randomBytes,
  randomUUID,
} from "node:crypto";

const action = process.argv[2] ?? "status";
if (!["status", "enable", "disable"].includes(action)) {
  throw new Error("usage: node scripts/fnos-ssh-control.mjs status|enable|disable");
}

const endpoint = process.env.FNOS_WEBSOCKET_URL;
const username = process.env.FNOS_USERNAME;
const password = process.env.FNOS_PASSWORD;
const debug = process.env.FNOS_DEBUG === "1";
if (!endpoint || !username || !password) {
  throw new Error(
    "FNOS_WEBSOCKET_URL, FNOS_USERNAME and FNOS_PASSWORD are required",
  );
}
const parsedEndpoint = new URL(endpoint);
if (!["ws:", "wss:"].includes(parsedEndpoint.protocol)) {
  throw new Error("FNOS_WEBSOCKET_URL must use ws:// or wss://");
}

let counter = 0;
function requestId() {
  counter += 1;
  return `${Date.now().toString(16)}-${counter.toString(16)}`;
}

function encryptLoginRequest(payload, publicKey) {
  const alphabet =
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const keyText = Array.from(randomBytes(32), (value) =>
    alphabet[value % alphabet.length]
  ).join("");
  const key = Buffer.from(keyText, "utf8");
  const iv = randomBytes(16);
  const rsa = publicEncrypt(
    {
      key: publicKey,
      padding: cryptoConstants.RSA_PKCS1_PADDING,
    },
    key,
  ).toString("base64");
  const cipher = createCipheriv("aes-256-cbc", key, iv);
  const aes = Buffer.concat([
    cipher.update(JSON.stringify(payload), "utf8"),
    cipher.final(),
  ]).toString("base64");
  return {
    key,
    iv,
    envelope: {
      req: "encrypted",
      iv: iv.toString("base64"),
      rsa,
      aes,
    },
  };
}

function decryptSessionSecret(ciphertext, key, iv) {
  const decipher = createDecipheriv("aes-256-cbc", key, iv);
  return Buffer.concat([
    decipher.update(Buffer.from(ciphertext, "base64")),
    decipher.final(),
  ]).toString("base64");
}

function signTokenRequest(payload, secret) {
  const serialized = JSON.stringify(payload);
  const signature = createHmac(
    "sha256",
    Buffer.from(secret, "base64"),
  ).update(serialized, "utf8").digest("base64");
  return `${signature}${serialized}`;
}

class FnosSocket {
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.pending = new Map();
  }

  async connect() {
    await new Promise((resolve, reject) => {
      const socket = new WebSocket(this.url);
      this.socket = socket;
      const timer = setTimeout(
        () => reject(new Error("fnOS WebSocket connection timeout")),
        10_000,
      );
      socket.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
      socket.addEventListener("error", () => {
        clearTimeout(timer);
        reject(new Error("fnOS WebSocket connection failed"));
      }, { once: true });
      socket.addEventListener("message", (event) => this.onMessage(event));
      socket.addEventListener("close", () => {
        for (const item of this.pending.values()) {
          clearTimeout(item.timer);
          item.reject(new Error("fnOS WebSocket closed"));
        }
        this.pending.clear();
      });
    });
  }

  onMessage(event) {
    let payload;
    try {
      payload = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (!payload.reqid) return;
    const item = this.pending.get(payload.reqid);
    if (!item) return;
    if (payload.result === "doing") return;
    clearTimeout(item.timer);
    this.pending.delete(payload.reqid);
    if (payload.result === "fail") {
      item.reject(
        new Error(
          `fnOS request failed (${item.req}): ${
            payload.errno ?? payload.code ?? "unknown"
          }`,
        ),
      );
      return;
    }
    item.resolve(payload);
  }

  request(req, params = {}, transform = null) {
    const reqid = requestId();
    const inner = { ...params, reqid, req };
    const outgoing = transform ? transform(inner) : inner;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(reqid);
        reject(new Error(`fnOS request timeout: ${req}`));
      }, 15_000);
      this.pending.set(reqid, { resolve, reject, timer, req });
      this.socket.send(
        typeof outgoing === "string" ? outgoing : JSON.stringify(outgoing),
      );
    });
  }

  close() {
    this.socket?.close();
  }
}

const client = new FnosSocket(endpoint);
try {
  await client.connect();
  const rsaInfo = await client.request("util.crypto.getRSAPub");
  if (!rsaInfo.pub || !rsaInfo.si) {
    throw new Error("fnOS RSA handshake returned incomplete data");
  }
  let loginCrypto;
  const login = await client.request(
    "user.login",
    {
      user: username,
      password,
      deviceType: "Browser",
      deviceName: "Windows-CodexMaintenance",
      did: randomUUID(),
      si: rsaInfo.si,
    },
    (payload) => {
      loginCrypto = encryptLoginRequest(payload, rsaInfo.pub);
      return loginCrypto.envelope;
    },
  );
  if (!login.token || !login.secret || !loginCrypto) {
    throw new Error("fnOS login did not return an authenticated session");
  }
  const sessionSecret = decryptSessionSecret(
    login.secret,
    loginCrypto.key,
    loginCrypto.iv,
  );
  const auth = await client.request(
    "user.authToken",
    { token: login.token, main: true, si: rsaInfo.si },
    (payload) => signTokenRequest(payload, sessionSecret),
  );
  if (debug) {
    process.stderr.write(`${JSON.stringify({
      step: "authToken",
      result: auth.result,
      errno: auth.errno,
      code: auth.code,
      hasBackId: Boolean(auth.backId),
      keys: Object.keys(auth).filter(
        (key) => !["token", "secret", "longToken"].includes(key),
      ),
    })}\n`);
  }

  const authenticatedRequest = (req, params = {}) =>
    client.request(
      req,
      params,
      (payload) => signTokenRequest(payload, sessionSecret),
    );
  const before = await authenticatedRequest("appcgi.network.ssh.status");
  if (action === "status") {
    process.stdout.write(JSON.stringify({ status: "ok", ssh: before.data }));
  } else {
    const desired = action === "enable";
    if (Boolean(before.data?.enable) !== desired) {
      await authenticatedRequest(
        "appcgi.network.ssh.switch",
        { enable: desired },
      );
    }
    const after = await authenticatedRequest("appcgi.network.ssh.status");
    if (Boolean(after.data?.enable) !== desired) {
      throw new Error(`fnOS SSH did not become ${action}d`);
    }
    process.stdout.write(
      JSON.stringify({
        status: "ok",
        changed: Boolean(before.data?.enable) !== desired,
        ssh: after.data,
      }),
    );
  }
} finally {
  client.close();
}
