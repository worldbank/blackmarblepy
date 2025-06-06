# CONTRIBUTING

Thank you for considering contributing! We appreciate your interest in helping us improve our project. By contributing, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

Please take a moment to review this document for important information on how to contribute effectively.

## How Can I Contribute?

There are several ways you can contribute to this project:

- **Bug Reports:** If you encounter a bug or unexpected behavior, please open an issue on our GitHub issue tracker. Be sure to include as much detail as possible to help us identify and fix the problem.

- **Feature Requests**: If you have an idea for a new feature or enhancement, please open an issue on our GitHub issue tracker and label it as a "feature request." Describe the feature and its use case in detail.

- **Pull Requests:** If you'd like to contribute code or documentation changes, we encourage you to submit a pull request (PR). Please follow the guidelines outlined in the [Contributing Code](#contributing-code) section below.

- **Documentation:** If you find any errors or have suggestions for improving our documentation, you can submit changes directly through a pull request.

- **Community Engagement:** Help answer questions and engage with other users and contributors on our GitHub Discussions (if applicable).

## Contributing Code

If you're contributing code, please follow these guidelines:

1. **Fork the Repository**: Click the "Fork" button on the top-right corner of this repository on GitHub. This will create a copy of the project in your GitHub account.

2. **Create a Branch:** Create a new branch for your feature or bug fix. Use a clear and descriptive name for your branch, like `feature/my-new-feature` or `bugfix/issue-123`.

3. **Make Changes:** Make your code changes and ensure they adhere to our coding standards.

4. **Test:** Ensure that your changes do not break existing functionality and add tests for new features or bug fixes.

5. **Commit and Push:** Commit your changes with a clear and concise commit message. Reference any related issues or pull requests in your commit message. Push your branch to your forked repository on GitHub.

6. **Create a Pull Request:** Open a pull request against the main branch of this repository. Provide a clear description of your changes and reference any relevant issues. Your PR will be reviewed by maintainers.

7. **Review and Iterate:** Expect feedback and be prepared to make additional changes if necessary. We may request changes, and once everything looks good, your PR will be merged.

### Installation

**BlackMarblePy** is available on [PyPI](https://pypi.org) as [blackmarblepy](https://pypi.org/project/blackmarblepy) and can installed using `pip`:

#### From PyPI

```shell
pip install blackmarblepy
```

#### From Source

1. Clone or download this repository to your local machine. Then, navigate to the root directory of the repository:

    ```shell
    git clone https://github.com/worldbank/blackmarblepy.git
    cd blackmarblepy
    ```

2. Create a virtual environment (optional but recommended):

    ```shell
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3. Install the package with dependencies:

    ```shell
    pip install .
    ```

    Install the package **in editable** mode with dependencies:

    ```shell
    pip install -e .
    ```

    The `-e` flag stands for "editable," meaning changes to the source code will immediately affect the installed package.

#### Building Documentation Locally

To build the documentation locally, after (1) and (2) above, please follow these steps:

- Install the package with documentation dependencies:

  ```shell
    pip install -e .[docs]
  ```

- Build the documentation:

  ```shell
    sphinx-build docs _build/html -b html
  ```

The generated documentation will be available in the `_build/html` directory. Open the `index.html` file in a web browser to view it.

## Code of Conduct

Please note that we have a [Code of Conduct](CODE_OF_CONDUCT.md) in place. We expect all contributors to adhere to it, both in interactions within this project and in interactions with other project members.

## Licensing

By contributing to this project, you agree that your contributions will be licensed under the project's [LICENSE](../LICENSE).
