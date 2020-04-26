# ha_erse
Home Assistant Custom Component for ERSE (Entidade Reguladora dos Serviços Energéticos)

This component provides the current tariff of a given electricity operator

This components is for energy clients in Portugal, and fully automates the transitions of tariffs of a utility_meter.

# Configuration

You can use a config flow (Configuration -> Integration) or you can setup through yaml:

## Configuration example

```yaml
sensor:
  - platform: erse
    operator: EDP
    plan: Bi-horário - ciclo diário
    utility_meters:
    - utility_meter.totalizador
```

Please note that using YAML a single `erse` entity can automate several utility_meters. Using the UI you will have to create multiple `erse` entities.

## Supported Plans

Go to https://github.com/dgomes/python-electricity/blob/master/README.md

Your operator is not there ? Open a PR or an Issue in the previous repository.
