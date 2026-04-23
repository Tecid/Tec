# Tick Volume Display Implementation Guide

This document provides instructions for implementing the tick volume data display in the frontend dashboard. The backend is already configured to collect this data from the MT5 terminal.

## Backend Context (Already Implemented)

We have already updated our worker process to capture the tick volume directly from the MT5 terminal. 

1. **`worker.py`:** The `get_tick_data` function successfully retrieves the `volume` from `mt5.symbol_info_tick()`:
   ```python
   def get_tick_data(symbol: str) -> dict | None:
       # ...
       tick = mt5.symbol_info_tick(symbol)
       return {
           "bid": tick.bid,
           "ask": tick.ask,
           "time": tick.time,
           "last": tick.last,
           "volume": tick.volume   # <--- Tick volume is successfully extracted here
       }
   ```

2. **IPC Communication:** The worker process sends this data via a pipe to `master.py` inside the worker loop (usually updating every 1ms):
   ```python
   data_pipe.send({
       "type": "TICK",
       "broker": broker_name,
       "data": tick
   })
   ```

3. **`master.py`:** The master component receives this `TICK` event and updates the internal state, making `volume` available alongside `bid` and `ask` prices. The data is available to be broadcasted to the frontend (likely through an existing REST endpoint or WebSocket context like `SocketContext.jsx`).

## Task for ChatGPT

1. **Review Frontend Architecture:** Check `client/src/pages/Dashboard.jsx` and `client/src/context/SocketContext.jsx` to see how real-time tick data (`bid`, `ask`) is currently being received from the backend. 
2. **Expose Volume (if needed):** If `server/bot_manager.py` or `server/api.py` filters the tick data being broadcasted, ensure `volume` is added to the broadcast payload.
3. **Frontend Integration:** Add a UI component or update the existing price widget in `Dashboard.jsx` to display the "Tick Volume" in real-time. Ensure it handles rapid updates gracefully without choking the React render cycle. 
4. **Styling:** Apply proper CSS (updating `client/src/components/Header.css` or equivalent) so the volume metric matches the dashboard's theme.
