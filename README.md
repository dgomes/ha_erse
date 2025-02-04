# ha_erse
Home Assistant Custom Component for ERSE (Entidade Reguladora dos Serviços Energéticos)

This component provides the current tariff of a given electricity operator as well as a simulation of the costs associated.

This components is for energy clients in Portugal, and fully automates the transitions of tariffs of a utility_meter.

# Configuration

Go to **Settings** >> **Devices & Services** in the UI. Click the button with `+` sign on the integrations page and from the list of integrations, select **ERSE**.

Type in your Energy Provider (EDP, GALP, Iberdrola), Power installed and the tariff plan and cycle (default is Ciclo Diário).

Then select which `utility_meters` are running through this electricity plan (this is optional and is only necessary to automate tariff change of the `utility_meter`)

Finally you must type in the cost in Euros of power availability and tariffs (Euro/kWh) as well as the entities that track each tariff.

**Important**

Your `utility_meter` must have the proper tarifs:
- Bi-Horário: `Vazio` e `Fora de Vazio`
- Tri-Horário: `Vazio`, `Ponta` e `Cheias`

That is it!

---

## **Detailed User Guide for Configuring HA_ERSE**

### Step 1: Create a Utility Meter Helper
1. Navigate to **Settings** → **Devices & Services** → **Helpers**.
2. Click **Add Helper** and select **Utility Meter**.
3. Fill in the following details:
   - **Name**: Enter a descriptive name (e.g., `Energia`).
   - **Input Sensor**: Select your energy sensor (e.g., `Shelly 3em Casa total active power`).
   - **Meter Reset Cycle**: Set this to `Monthly`.
   - **Meter Reset Offset**: Enter the day your electricity bill resets (e.g., `22`).
   - **Supported Tariffs**: Add `Vazio` and `Fora de Vazio` for Bi-Horário plans.
4. Enable **Net Consumption** if you use solar energy.
5. Save the utility meter.

![image](https://github.com/user-attachments/assets/4de9cf42-f554-496d-b6ab-b19c4836898b)
![image](https://github.com/user-attachments/assets/38868198-225f-4b8e-b094-0dded0e765aa)


---

### Step 2: Initialize Tariffs
1. After creating the helper, ensure both tariffs have values:
   - Go to the **Sensors** configuration (e.g., your Shelly 3em sensor).
   - Manually switch between the tariffs `Vazio` and `Fora de Vazio` for a few minutes each.
2. This step initializes the tariffs, which are required for HA_ERSE to function correctly.

---

### Step 3: Configure HA_ERSE
1. Go to **Settings** → **Devices & Services** → **Integrations**.
2. Add the HA_ERSE integration and configure:
   - **Operator Name**: Enter your electricity provider (e.g., `EDP`).
   - **Installed Power**: Set the value from your contract (e.g., `13.8 kVA`).
   - **Plan**: Select your tariff plan (e.g., `Bi-Horário`).
   - **Cycle**: Choose the billing cycle (`Ciclo Semanal` or `Ciclo Diário`).
3. Select the **Utility Meter** created earlier.
4. Configure costs and sensors:
   - Enter the cost per kWh for `Vazio` and `Fora de Vazio` tariffs.
   - Assign the appropriate sensors for each tariff (e.g., `Energia Vazio` and `Energia Fora de Vazio`).

![image](https://github.com/user-attachments/assets/c143e0aa-6752-40bd-b299-a8ee6234142c)
![image](https://github.com/user-attachments/assets/576a2787-bbee-4560-96e9-12f3f25d86b7)

---

### Step 4: Add to Energy Dashboard
1. Navigate to **Settings** → **Dashboards** → **Energy**.
2. Under **Grid Consumption**, add:
   - The `Vazio` tariff with its balance sensor.
   - The `Fora de Vazio` tariff with its balance sensor.
3. If using solar energy, configure **Return to Grid** using the appropriate sensor (e.g., `Shelly 3em Casa total active returned energy`).

![image](https://github.com/user-attachments/assets/0fc1c8a3-2b39-4afb-b7c6-71af5b160cd5)
![image](https://github.com/user-attachments/assets/80e396db-e2b7-49fb-af2e-e36e3a632c2d)


---

## Example `utility_meter` configuration

```
utility_meter:            
  daily_energy:                         
    source: sensor.energia_rede_importada
    cycle: daily                       
    tariffs:
      - Fora de Vazio
      - Vazio 
  monthly_energy:
    source: sensor.energia_rede_importada
    cycle: monthly
    tariffs:        
      - Fora de Vazio                                        
      - Vazio        
    offset:           
      days: 20           
```

For more information go the [utility meter help page](https://www.home-assistant.io/integrations/utility_meter/)

# Help

Join me at [CPHA Discord](https://discord.gg/Mh9mTEA)
