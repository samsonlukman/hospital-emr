# Bahmni Docker

Refer this [Wiki Page](https://bahmni.atlassian.net/wiki/spaces/BAH/pages/299630726/Running+Bahmni+on+Docker) for Running Bahmni on Docker for detailed instructions.

## Running Bahmni LITE or STANDARD using docker compose: 
1. Navigate to the relevant subfolder for your desired configuration. For example: `cd bahmni-lite`.
2. Execute the script: `./run-bahmni.sh`. This script provides various options such as start, stop, view logs, pull updates, reset, etc.
3. Before executing the above commands, ensure that your local environment file in the sub-folder is correctly configured with the appropriate profile.

Alternatively, if you wish to use docker compose commands directly, you can use the --env-file option to pass the environment variables files:
```shell
docker compose up --env-file .env
```

## Environment Variable Configuration

The tracked `.env` and `.env.dev` files contain public development defaults and must not be used for a hospital deployment. They remain tracked because the upstream development deployment workflows currently depend on them.

For a hospital deployment:

1. Copy the relevant `bahmni-lite/.env.example` or `bahmni-standard/.env.example` to an untracked deployment environment file.
2. Supply every blank identity, password, token, and key through the deployment's existing secret mechanism.
3. Use unique values for that deployment; never commit the populated file.
4. Rotate all tracked development credentials before hospital use.

Hospital EMR's backend additionally requires an ignored `bahmni-standard/.env.abikan`; copy `.env.abikan.example` and populate it locally or inject the same variable names through deployment secrets. The backend refuses to start unless `ABIKAN_ENVIRONMENT` and all required service identity variables are present. Production also rejects well-known development/default values.

The `.env` and `.env.dev` files are used for configuring environment variables for the Bahmni Lite development setup.

The `.env` file points to the `1.0.0` image tag, which represents the stable and tested version of Bahmni Lite v1.0.0. Its image selections may inform deployment configuration, but its tracked credentials are development-only.
The `.env.dev` file points to the `latest` image version, which provides the most recent updates for development and testing purposes.

- By default `run-bahmni.sh` script runs with the `.env`, that uses the `1.0.0` images
```shell
run-bahmni.sh
```

- Instead if you wish to use the `latest` images, run the `run-bahmni.sh` script with the argument `.env.dev`
```shell
run-bahmni.sh .env.dev
```

- Additionally, you have the flexibility to create your own environment variable configuration. To do this, create a custom a `.env` file (eg: `.env.local`) and run the run-bahmni.sh script with the `.env.local` argument:
```shell
run-bahmni.sh .env.local
```

Please choose the appropriate environment variables file based on your requirements and make sure the respective `.env` or `.env-dev` file is properly configured before running the commands.

For detailed instructions and further information, please refer to the [Wiki Page](https://bahmni.atlassian.net/wiki/spaces/BAH/pages/299630726/Running+Bahmni+on+Docker) mentioned above.
