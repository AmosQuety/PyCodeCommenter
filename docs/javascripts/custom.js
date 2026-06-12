document.addEventListener('DOMContentLoaded', () => {
  const providerSelect = document.getElementById('ci-provider');
  const managerSelect = document.getElementById('ci-manager');
  const levelSelect = document.getElementById('ci-level');
  const outputCode = document.getElementById('ci-output');

  if (!providerSelect || !managerSelect || !levelSelect || !outputCode) return;

  const updateSnippet = () => {
    const provider = providerSelect.value;
    const manager = managerSelect.value;
    const level = levelSelect.value;

    let installCmd = 'pip install pycodecommenter';
    if (manager === 'poetry') {
      installCmd = 'poetry add pycodecommenter --group dev';
    } else if (manager === 'uv') {
      installCmd = 'uv pip install pycodecommenter';
    }

    let runCmd = 'pycodecommenter validate src/';
    if (level === 'warn') {
      runCmd = 'pycodecommenter validate src/ || exit 0';
    }

    let snippet = '';

    if (provider === 'github') {
      snippet = `# .github/workflows/docs-check.yml
name: Documentation Check
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install PyCodeCommenter
        run: ${installCmd}
      - name: Check for documentation issues
        run: ${runCmd}`;
    } else if (provider === 'gitlab') {
      snippet = `# .gitlab-ci.yml
docs-check:
  image: python:3.11
  script:
    - ${installCmd}
    - ${runCmd}
`;
    }

    outputCode.textContent = snippet;
  };

  providerSelect.addEventListener('change', updateSnippet);
  managerSelect.addEventListener('change', updateSnippet);
  levelSelect.addEventListener('change', updateSnippet);
});
