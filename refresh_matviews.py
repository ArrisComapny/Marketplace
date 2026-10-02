import time
import logging

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import DbConnection

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)

# Порядок важен: vendor_code — справочник, который могут использовать остальные
MATVIEWS = [
    'vendor_code_mat',
    'stocks_view_final_mat',
    'wb_services_final_mat',
]


def refresh_matviews(matviews: list[str] = None, db_conn: DbConnection = None, retries: int = 6) -> None:
    """
        Обновление материализованных представлений.

        Args:
            matviews (list[str]): Какие представления обновить. По умолчанию — все (MATVIEWS).
            db_conn (DbConnection): Готовое соединение; без него создаётся своё.
            retries (int): Попытки при недоступной базе.
    """
    matviews = matviews or MATVIEWS
    try:
        if db_conn is None:
            db_conn = DbConnection()

        for matview in matviews:
            start = time.time()
            logger.info(f"Обновляю {matview}")
            db_conn.session.execute(text(f'REFRESH MATERIALIZED VIEW public.{matview}'))
            db_conn.session.commit()
            logger.info(f"{matview} обновлено за {time.time() - start:.1f} с")

        # Полное перестроение таблицы wb_main_table_final2 (функция в БД)
        start = time.time()
        logger.info("Выполняю refresh_wb_main_table_final2_full()")
        db_conn.session.execute(text('SELECT refresh_wb_main_table_final2_full()'))
        db_conn.session.commit()
        logger.info(f"wb_main_table_final2 обновлена за {time.time() - start:.1f} с")
    except OperationalError:
        logger.error(f'Не доступна база данных. Осталось попыток подключения: {retries - 1}')
        if retries > 0:
            time.sleep(10)
            refresh_matviews(matviews=matviews, retries=retries - 1)
    except Exception as e:
        logger.error(f'{e}')


if __name__ == "__main__":
    refresh_matviews()
