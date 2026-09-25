/** Artificial profile for demonstrating request shape; no formulation output. */
export async function validateArtificialProfile(client) {
  return client.call('selected_ingredient_meals__validateQuickMealProfile', {
    body: { profile: { species: 'DOG', weight_kg: 10 } },
  });
}
