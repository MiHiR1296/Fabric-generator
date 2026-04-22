import { expect, test } from 'playwright/test';

const PNG_BUFFER = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sXG9WQAAAAASUVORK5CYII=',
  'base64',
);

test('walks through yarn upload, color mapping, and Blender preview rendering', async ({ page }) => {
  let yarnAssets: Array<Record<string, unknown>> = [];
  let renderJob: Record<string, unknown> | null = null;
  let renderPayload: Record<string, unknown> | null = null;

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

  await page.route('**/api/blender/render-project', async (route) => {
    renderPayload = route.request().postDataJSON() as Record<string, unknown>;
    renderJob = {
      id: 'job-1',
      status: 'queued',
      message: 'Render job queued. Blender will build the draft and render a preview next.',
      draftTitle: 'Untitled Draft',
      targetObjectName: 'ParametricWeave',
      draftObjectName: 'WebDraft_Live',
      createdAt: '2026-04-22T00:00:00Z',
      imageUrl: null,
      logTail: [],
    };
    await route.fulfill({ json: renderJob });
  });

  await page.route('**/api/blender/render-jobs/job-1', async (route) => {
    renderJob = {
      ...renderJob,
      status: 'succeeded',
      message: 'Preview render ready.',
      imageUrl: '/api/blender/render-jobs/job-1/image',
      logTail: ['render complete'],
    };
    await route.fulfill({ json: renderJob });
  });

  await page.route('**/api/blender/render-jobs/job-1/image', async (route) => {
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
    '2 slots still need yarn assignments before rendering.',
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

  await expect(page.getByTestId('render-status-message')).toContainText('Render job queued');
  await expect(page.locator('.render-preview__image')).toBeVisible();
  await expect(page.getByTestId('render-status-message')).toContainText('Preview render ready.');

  expect(Array.isArray(renderPayload?.colorBindings)).toBeTruthy();
  expect((renderPayload?.colorBindings as Array<unknown>).length).toBe(2);
  expect(renderPayload?.target_object_name).toBe('ParametricWeave');
});
