-- Starter universe. `state` = primary manufacturing/HQ state used to join
-- POSOCO state-level industrial power demand to companies (idea.md §4: state
-- granularity is the honest ceiling for POSOCO).
-- Expanding coverage = adding rows here, never code changes.
INSERT INTO universe (ticker, name, sector, state) VALUES
  ('ULTRACEMCO','UltraTech Cement','Cement','Gujarat'),
  ('SHREECEM','Shree Cement','Cement','Rajasthan'),
  ('AMBUJACEM','Ambuja Cements','Cement','Gujarat'),
  ('ACC','ACC','Cement','Maharashtra'),
  ('DALBHARAT','Dalmia Bharat','Cement','Tamil Nadu'),
  ('TATASTEEL','Tata Steel','Metals','Jharkhand'),
  ('JSWSTEEL','JSW Steel','Metals','Karnataka'),
  ('SAIL','Steel Authority of India','Metals','Chhattisgarh'),
  ('JINDALSTEL','Jindal Steel & Power','Metals','Chhattisgarh'),
  ('HINDALCO','Hindalco Industries','Metals','Maharashtra'),
  ('TATAMOTORS','Tata Motors','Auto','Maharashtra'),
  ('M&M','Mahindra & Mahindra','Auto','Maharashtra'),
  ('BAJAJ-AUTO','Bajaj Auto','Auto','Maharashtra'),
  ('MARUTI','Maruti Suzuki','Auto','Haryana'),
  ('HEROMOTOCO','Hero MotoCorp','Auto','Haryana'),
  ('EICHERMOT','Eicher Motors','Auto','Tamil Nadu'),
  ('TVSMOTOR','TVS Motor','Auto','Tamil Nadu'),
  ('NTPC','NTPC','Power','Delhi'),
  ('POWERGRID','Power Grid Corp','Power','Haryana'),
  ('TATAPOWER','Tata Power','Power','Maharashtra'),
  ('ADANIPOWER','Adani Power','Power','Gujarat'),
  ('GRASIM','Grasim Industries','Materials','Maharashtra'),
  ('ASIANPAINT','Asian Paints','Materials','Maharashtra'),
  ('UPL','UPL','Chemicals','Gujarat'),
  ('PIDILITIND','Pidilite Industries','Chemicals','Maharashtra'),
  ('RELIANCE','Reliance Industries','Energy','Gujarat'),
  ('ONGC','Oil & Natural Gas Corp','Energy','Uttarakhand'),
  ('COALINDIA','Coal India','Energy','West Bengal'),
  ('LT','Larsen & Toubro','Infra','Maharashtra'),
  ('SIEMENS','Siemens India','Infra','Maharashtra')
ON CONFLICT (ticker) DO UPDATE
  SET name = EXCLUDED.name,
      sector = EXCLUDED.sector,
      state  = EXCLUDED.state;
