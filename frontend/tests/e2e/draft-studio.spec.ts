import { expect, test } from 'playwright/test';

const PNG_BUFFER = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sXG9WQAAAAASUVORK5CYII=',
  'base64',
);

test('walks through yarn upload, color mapping, and lazy Blender material preview', async ({ page }) => {
  let yarnAssets: Array<Record<string, unknown>> = [];
  let previewPayload: Record<string, unknown> | null = null;

  await page.route('**/api/parser/health', async (route) => {
    await route.fulfill({ json: { status: 'ok' } });
  });

  await page.route('**/api/yarn/assets/*/files/*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: PNG_BUFFER,
    });
  });

  await page.route('**/api/yarn/assets', async (route) => {
    if (route.request().method() === 'POST') {
      yarnAssets = [
        {
          id: 'yarn-1',
          label: 'Warp Cotton',
          status: 'ready',
          sourceUrl: '/api/yarn/assets/yarn-1/files/source.png',
          diffuseUrl: '/api/yarn/assets/yarn-1/files/diffuse.png',
          alphaUrl: '/api/yarn/assets/yarn-1/files/alpha.png',
          preprocessMeta: { stage: 'done' },
          alphaMeta: { stage: 'done' },
        },
      ];
      await route.fulfill({ json: yarnAssets });
      return;
    }

    await route.fulfill({ json: yarnAssets });
  });

  await page.route('**/api/blender/live-preview', async (route) => {
    previewPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        sessionId: 'default',
        status: 'ready',
        message: 'Blender camera preview updated.',
        targetObjectName: 'ParametricWeave',
        draftObjectName: 'WebDraft_Live',
        updatedAt: '2026-04-22T12:00:00Z',
        imageUrl: '/api/blender/live-preview/default/image?v=2026-04-22T12:00:00Z',
        width: 1024,
        height: 768,
      },
    });
  });

  await page.route('**/api/blender/live-preview/default/image*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: PNG_BUFFER,
    });
  });

  await page.goto('/');

  await expect(page.getByTestId('fabric-studio-app')).toBeVisible();
  await expect(page.getByText('One-Point Fabric Studio')).toBeVisible();
  await expect(page.getByTestId('yarn-empty-state')).toContainText('No yarn assets yet');
  await expect(page.getByTestId('render-preview-button')).toBeDisabled();

  await page.getByTestId('yarn-upload-input').setInputFiles({
    name: 'sample-yarn.png',
    mimeType: 'image/png',
    buffer: PNG_BUFFER,
  });

  await expect(page.getByTestId('yarn-library-step')).toContainText('Queued 1 yarn asset');
  await expect(page.getByTestId('yarn-asset-card')).toContainText('Warp Cotton');
  await expect(page.getByTestId('binding-status-message')).toContainText(
    '2 slots still need yarn assignments before previewing.',
  );

  const bindingSelects = page.locator('[data-testid^="binding-select-"]');
  await expect(bindingSelects).toHaveCount(2);
  await bindingSelects.nth(0).selectOption('yarn-1');
  await bindingSelects.nth(1).selectOption('yarn-1');

  await expect(page.getByTestId('binding-status-message')).toContainText(
    'Every visible draft color is assigned to a processed yarn asset.',
  );
  await expect(page.getByTestId('render-preview-button')).toBeEnabled();

  await page.getByTestId('render-preview-button').click();

  await expect(page.getByTestId('render-status-message')).toContainText('Blender camera preview updated.');
  await expect(page.locator('.render-preview__image')).toBeVisible();
  await expect(page.getByTestId('render-controls-note')).toContainText('No unsent control edits right now.');

  expect(Array.isArray(previewPayload?.colorBindings)).toBeTruthy();
  expect((previewPayload?.colorBindings as Array<unknown>).length).toBe(2);
  expect(previewPayload?.target_object_name).toBe('ParametricWeave');
});
