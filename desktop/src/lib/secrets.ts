export interface SecretListing {
  key: string;
  hint: string;
  updatedAt: string;
}

export interface SecretEntry {
  hint: string;
  updatedAt: string;
  cipher: string;
}

export interface CorruptionRecovery {
  backupPath: string;
  recoveredAt: string;
}

export interface SecretsAvailability {
  available: boolean;
  filePath: string;
  corruptionRecovery: CorruptionRecovery | null;
}

function bridge() {
  if (!window.tradingAgentsLab?.secrets) {
    throw new Error('secrets bridge not available — preload not loaded');
  }
  return window.tradingAgentsLab.secrets;
}

export function getAvailability(): Promise<SecretsAvailability> {
  return bridge().availability();
}

export function setSecret(key: string, value: string): Promise<SecretEntry> {
  return bridge().set(key, value);
}

export function getSecret(key: string): Promise<string | null> {
  return bridge().get(key);
}

export function listSecrets(): Promise<SecretListing[]> {
  return bridge().list();
}

export function deleteSecret(key: string): Promise<boolean> {
  return bridge().delete(key);
}

export function onSecretsRecovered(
  handler: (info: CorruptionRecovery) => void,
): () => void {
  return bridge().onRecovered(handler);
}
