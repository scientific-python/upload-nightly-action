// Loaded by the "Report upload status" step in ../action.yml via actions/github-script:
//
//   await require(`${process.env.GITHUB_ACTION_PATH}/scripts/report_failure.js`)({ github, context, core })
//
// Opens a tracking issue on the repository running the action when the nightly
// upload fails, and closes it again on the next successful upload. Idempotent:
// an existing open issue (matched by label) is reused rather than duplicated.
//
// Inputs are read from the environment set by the workflow step:
//   UPLOAD_OUTCOME     'failure' or 'success'
//   ISSUE_REPOSITORY   optional "owner/name" override for where to open the issue

'use strict';

const LABEL = 'nightly-upload-failure';
const TITLE = '🌙 Nightly wheel upload is failing';

module.exports = async ({ github, context, core }) => {
  let owner = context.repo.owner;
  let repo = context.repo.repo;
  const override = (process.env.ISSUE_REPOSITORY || '').trim();
  if (override.includes('/')) {
    [owner, repo] = override.split('/');
  }

  const runUrl =
    `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}` +
    `/actions/runs/${process.env.GITHUB_RUN_ID}`;

  // Make sure the tracking label exists before we filter/create by it.
  try {
    await github.rest.issues.getLabel({ owner, repo, name: LABEL });
  } catch (err) {
    if (err.status === 404) {
      await github.rest.issues.createLabel({
        owner,
        repo,
        name: LABEL,
        color: 'b60205',
        description: 'Automatically opened when a nightly wheel upload fails.',
      });
    } else {
      throw err;
    }
  }

  const open = (
    await github.paginate(github.rest.issues.listForRepo, {
      owner,
      repo,
      state: 'open',
      labels: LABEL,
      per_page: 100,
    })
  ).filter((i) => !i.pull_request);

  if (process.env.UPLOAD_OUTCOME === 'failure') {
    if (open.length) {
      core.info(`A failure issue is already open (#${open[0].number}).`);
      return;
    }
    const body = [
      'The nightly wheel upload performed by ' +
        '[`scientific-python/upload-nightly-action`]' +
        '(https://github.com/scientific-python/upload-nightly-action) failed.',
      '',
      'No fresh nightly wheels were published for this project. Downstream ' +
        'projects that test against these nightly wheels may start failing ' +
        'until the upload succeeds again.',
      '',
      `Failing workflow run: ${runUrl}`,
      '',
      'This issue was opened automatically and will be closed automatically ' +
        'on the next successful upload.',
    ].join('\n');
    const created = await github.rest.issues.create({
      owner,
      repo,
      title: TITLE,
      body,
      labels: [LABEL],
    });
    core.info(`Opened failure issue #${created.data.number}.`);
  } else {
    for (const issue of open) {
      await github.rest.issues.createComment({
        owner,
        repo,
        issue_number: issue.number,
        body:
          '✅ Nightly wheel upload succeeded again; closing automatically.\n\n' +
          `Successful run: ${runUrl}`,
      });
      await github.rest.issues.update({
        owner,
        repo,
        issue_number: issue.number,
        state: 'closed',
        state_reason: 'completed',
      });
      core.info(`Closed failure issue #${issue.number}.`);
    }
  }
};
