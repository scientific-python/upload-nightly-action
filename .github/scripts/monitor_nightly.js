// Loaded by monitor-nightly.yml via actions/github-script:
//
//   await require(`${process.env.GITHUB_WORKSPACE}/.github/scripts/monitor_nightly.js`)({ github, context, core })
//
// Watches the scientific-python-nightly-wheels channel and files issues on this
// repository when a package stops receiving uploads:
//   * > 30 days without an upload -> open a "stale" issue (auto-closed on recovery)
//   * > 60 days without an upload -> additionally open a "purge candidate" issue.
//
// Never deletes anything (that is remove-wheels.yml's job); packages listed in
// packages-ignore-from-cleanup.txt are intentionally exempt and are skipped.

'use strict';

const ORG = 'scientific-python-nightly-wheels';
const STALE_DAYS = 30;
const PURGE_DAYS = 60;
const STALE_LABEL = 'stale-nightly';
const PURGE_LABEL = 'nightly-purge-candidate';
const DAY_MS = 24 * 60 * 60 * 1000;

const marker = (name, kind) => `<!-- nightly-monitor:${name}:${kind} -->`;

async function getJSON(url) {
  const resp = await fetch(url, {
    headers: { Accept: 'application/json', 'User-Agent': 'upload-nightly-action-monitor' },
  });
  if (!resp.ok) throw new Error(`${url} -> HTTP ${resp.status}`);
  return resp.json();
}

// Packages intentionally exempt from cleanup (e.g. rarely-updated ones) should
// not be flagged as stale. Reuse the same list that remove-wheels.yml honors.
// The repository is checked out, so the file is read directly from disk.
function loadIgnoreList(core) {
  const fs = require('fs');
  const ignore = new Set();
  const path = `${process.env.GITHUB_WORKSPACE}/packages-ignore-from-cleanup.txt`;
  try {
    for (const line of fs.readFileSync(path, 'utf8').split('\n')) {
      const name = line.trim();
      if (name && !name.startsWith('#')) ignore.add(name);
    }
    core.info(`Ignoring ${ignore.size} exempt package(s): ${[...ignore].join(', ')}`);
  } catch (err) {
    core.warning(`Could not read ${path}: ${err.message}; proceeding without an ignore list.`);
  }
  return ignore;
}

module.exports = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;

  async function ensureLabel(name, color, description) {
    try {
      await github.rest.issues.getLabel({ owner, repo, name });
    } catch (err) {
      if (err.status === 404) {
        await github.rest.issues.createLabel({ owner, repo, name, color, description });
      } else {
        throw err;
      }
    }
  }

  async function openIssuesWithLabel(label) {
    const list = await github.paginate(github.rest.issues.listForRepo, {
      owner,
      repo,
      state: 'open',
      labels: label,
      per_page: 100,
    });
    return list.filter((i) => !i.pull_request);
  }

  async function ensureOpen(list, name, kind, title, body, label) {
    const m = marker(name, kind);
    if (list.some((i) => (i.body || '').includes(m))) {
      core.info(`Issue already open for ${name} (${kind}).`);
      return;
    }
    const created = await github.rest.issues.create({
      owner,
      repo,
      title,
      labels: [label],
      body: `${m}\n\n${body}`,
    });
    core.info(`Opened ${kind} issue #${created.data.number} for ${name}.`);
  }

  async function closeIfOpen(list, name, kind, comment) {
    const m = marker(name, kind);
    for (const issue of list.filter((i) => (i.body || '').includes(m))) {
      await github.rest.issues.createComment({
        owner,
        repo,
        issue_number: issue.number,
        body: comment,
      });
      await github.rest.issues.update({
        owner,
        repo,
        issue_number: issue.number,
        state: 'closed',
        state_reason: 'completed',
      });
      core.info(`Closed ${kind} issue #${issue.number} for ${name}.`);
    }
  }

  const ignore = loadIgnoreList(core);

  await ensureLabel(
    STALE_LABEL,
    'fbca04',
    'A nightly package has not received an upload in over 30 days.',
  );
  await ensureLabel(
    PURGE_LABEL,
    'd93f0b',
    'A nightly package has not received an upload in over 60 days.',
  );

  const packages = await getJSON(`https://api.anaconda.org/packages/${ORG}`);
  core.info(`Found ${packages.length} packages in ${ORG}.`);

  const staleOpen = await openIssuesWithLabel(STALE_LABEL);
  const purgeOpen = await openIssuesWithLabel(PURGE_LABEL);
  const now = Date.now();
  const summary = [];

  for (const pkg of packages) {
    const name = pkg.name;
    if (ignore.has(name)) {
      core.info(`Skipping exempt package ${name}.`);
      continue;
    }

    let files;
    try {
      const detail = await getJSON(`https://api.anaconda.org/package/${ORG}/${name}`);
      files = detail.files || [];
    } catch (err) {
      core.warning(`Could not fetch details for ${name}: ${err.message}`);
      continue;
    }

    const times = files
      .map((f) => Date.parse((f.upload_time || '').replace(' ', 'T')))
      .filter((t) => !Number.isNaN(t));
    if (!times.length) {
      core.warning(`No dated files for ${name}; skipping.`);
      continue;
    }

    const latest = Math.max(...times);
    const ageDays = Math.floor((now - latest) / DAY_MS);
    const lastUpload = new Date(latest).toISOString().slice(0, 10);
    summary.push({ name, ageDays, lastUpload });

    const indexHint =
      `python -m pip install ${name} --pre --upgrade ` +
      `--index-url https://pypi.anaconda.org/${ORG}/simple ` +
      `--extra-index-url https://pypi.org/simple`;

    // --- 30 day stale issue -------------------------------------------------
    if (ageDays > STALE_DAYS) {
      await ensureOpen(
        staleOpen,
        name,
        'stale',
        `📦 \`${name}\`: no nightly upload in over ${STALE_DAYS} days`,
        [
          `The package \`${name}\` has not received a nightly wheel upload in ` +
            `**${ageDays} days** (last upload: ${lastUpload}).`,
          '',
          "The producing project's nightly build is most likely failing. Please " +
            'check its CI and restore the nightly upload.',
          '',
          `Latest files: https://anaconda.org/${ORG}/${name}/files`,
          '',
          'This issue was opened automatically and will be closed automatically ' +
            'once a fresh upload lands.',
        ].join('\n'),
        STALE_LABEL,
      );
    } else {
      await closeIfOpen(
        staleOpen,
        name,
        'stale',
        `✅ \`${name}\` received a fresh nightly upload (${lastUpload}); closing automatically.`,
      );
    }

    // --- 60 day purge issue -------------------------------------------------
    if (ageDays > PURGE_DAYS) {
      await ensureOpen(
        purgeOpen,
        name,
        'purge',
        `🗑️ \`${name}\`: consider purging from the nightly channel (${ageDays} days stale)`,
        [
          `The package \`${name}\` has not received a nightly wheel upload in ` +
            `**${ageDays} days** (last upload: ${lastUpload}), which is beyond the ` +
            `${PURGE_DAYS}-day threshold.`,
          '',
          'Maintainers: please decide whether to **purge this package from the ' +
            'nightly channel** until its build is fixed. Long-stale wheels are no ' +
            'longer "nightly" and can silently mask upstream breakage for downstream ' +
            'users who install with:',
          '',
          '```',
          indexHint,
          '```',
          '',
          'If this package is intentionally kept despite being stale, add it to ' +
            '`packages-ignore-from-cleanup.txt` to silence this monitor.',
          '',
          'If the nightly build is restored, this issue will be closed automatically.',
        ].join('\n'),
        PURGE_LABEL,
      );
    } else {
      await closeIfOpen(
        purgeOpen,
        name,
        'purge',
        `✅ \`${name}\` received a fresh nightly upload (${lastUpload}); closing automatically.`,
      );
    }
  }

  summary.sort((a, b) => b.ageDays - a.ageDays);
  await core.summary
    .addHeading(`Nightly channel freshness (${ORG})`)
    .addTable([
      [
        { data: 'Package', header: true },
        { data: 'Age (days)', header: true },
        { data: 'Last upload', header: true },
      ],
      ...summary.map((s) => [s.name, String(s.ageDays), s.lastUpload]),
    ])
    .write();
};
