from dotenv import load_dotenv


def sync():
    load_dotenv()
    from broker import Broker
    import config
    import orders
    broker = Broker(env=config.ALPACA_ENV)
    return orders.sync_state(broker, alerts=[])
