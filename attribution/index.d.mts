import type { RuntimeStatus } from '../sdk/client.mjs';
export const attributionText: Readonly<{ en: string; zh: string }>;
export function createAttribution(options?: { document?: Document; locale?: 'en' | 'zh' }): HTMLSpanElement;
export function requiresAttribution(status?: RuntimeStatus): boolean;
