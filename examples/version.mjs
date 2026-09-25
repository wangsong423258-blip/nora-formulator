/** Supply an authenticated client; this module performs no work when imported. */
export async function readVersion(client) {
  const response = await client.version();
  return response.metadata;
}
