# ha_erse
Home Assistant Custom Component for ERSE (Entidade Reguladora dos Serviços Energéticos)

This component provides the current tariff of a given electricity operator

This components is for energy clients in Portugal, and fully automates the transitions of tariffs of a utility_meter.

# Configuration

Go to **Configuration** >> **Integrations** in the UI. Click the button with `+` sign on the integrations page and from the list of integrations, select **ERSE**.

Pick your Energy Provider (EDP, GALP, Iberdrola) and the tariff plan (all plans from all operators are listed).

Then select which `utility_meters` are running through this electricity plan (you can choose multiple)

**Important**

Your `utility_meter` must have the proper tarifs:
- Bi-Horário: `Vazio` e `Fora de Vazio`
- Tri-Horário: `Vazio`, `Ponta` e `Cheias`

That is it!

# Help

Join me at [CPHA Discord](https://discord.gg/Mh9mTEA)
