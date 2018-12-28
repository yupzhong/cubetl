# CubETL
# Copyright (c) 2013-2019 Jose Juan Montes

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import logging
from cubetl import olap, flow
import cubetl
from cubetl.sql import sql, schemaimport
from cubetl.olap import sql as olapsql, HierarchyDimension, Key
from cubetl.olap.sql import OlapMapping
from cubetl.core import Component

from sqlalchemy.engine import create_engine
import slugify
import sqlalchemy

from cubetl import olap, cubes
from cubetl.flow import Chain
from cubetl.util.config import PrintConfig
from cubetl.util import Print, PrettyPrint
from cubetl.sql import sql
from cubetl.olap.sql import OlapMapping
from cubetl.olap import Measure, Key, Attribute
from cubetl.text import functions
import re


# Get an instance of a logger
logger = logging.getLogger(__name__)


class DBToSQL(Component):
    """
    Connects to a database through a connection and generates CubETL objects
    that represent the tables and columns.

    This object can be used at configuration time before initialization of components,
    see the `sql2cubetl` method.
    """

    sql2cubetl_options_default = {'db2sql.ignore_tables': ['^sqlite_.*$']}

    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    def process(self, ctx, m):
        DBToSQL.db2sql(ctx, self.connection)
        yield m

    @staticmethod
    def db2sql(ctx, connection, options=None, debug=False, prefix='db2sql'):
        """
        Config is a dictionary with settings:
            {'db2sql.ignore_tables': [r'^session_.*$']}
        """

        if options is None:
            options = DBToSQL.sql2cubetl_options_default

        connection.url = ctx.interpolate(None, connection.url)
        engine = connection.engine()  # create_engine(ctx.interpolate(None, connection.url))
        metadata = sqlalchemy.MetaData()
        metadata.reflect(engine)

        #connection_urn = "%s.conn" % prefix # .%s" % (prefix, db_url)
        #connection = ctx.add(connection_urn, sql.Connection(url=engine.url))

        #cubetlconfig.load_config(ctx, os.path.dirname(__file__) + "/cubetl-datetime.yaml")
        #ctx.register('cubetl.datetime')
        #ctx.register(connection)

        # Load yaml library definitions that are dependencies

        logger.info("Importing CubETL SQL schema from database: %s" % engine.url)

        for dbtable in metadata.sorted_tables:

            ignored = False
            ignore_re_list = options.get('db2sql.ignore_tables', [])
            for ignore_re in ignore_re_list:
                if re.match(ignore_re, dbtable.name):
                    ignored = True

            if ignored:
                logger.info("Ignored table: %s" % dbtable.name)
                continue

            logger.info("Table: %s" % dbtable.name)

            #tablename = slugify.slugify(dbtable.name, separator="_")

            columns = []

            for dbcol in dbtable.columns:

                #if dbcol.name in exclude_columns:
                #    logger.info()
                #    continue

                logger.info("Column: %s [type=%s, null=%s, pk=%s, fk=%s]" % (dbcol.name, coltype(dbcol), dbcol.nullable, dbcol.primary_key, dbcol.foreign_keys))

                if dbcol.primary_key:
                    column = cubetl.sql.sql.SQLColumn(name=dbcol.name,
                                                      pk=True, type=coltype(dbcol))

                elif dbcol.foreign_keys and len(dbcol.foreign_keys) > 0:

                    if len(dbcol.foreign_keys) > 1:
                        # TODO: Support this
                        raise Exception("Multiple foreign keys found for column: %s" % (dbcol.name))

                    foreign_sqlcolumn_name = "%s.table.%s.col.%s" % (prefix, list(dbcol.foreign_keys)[0].column.table.name, list(dbcol.foreign_keys)[0].column.name)
                    foreign_sqlcolumn = ctx.get(foreign_sqlcolumn_name, fail=False)

                    if not foreign_sqlcolumn and (True):
                        logger.warn("Skipped foreign key %s in table %s, as foreign key column (%s.%s) was not found.", dbcol.name, dbtable.name, list(dbcol.foreign_keys)[0].column.table.name, list(dbcol.foreign_keys)[0].column.name)
                        continue

                    column = cubetl.sql.sql.SQLColumnFK(name=dbcol.name, label=functions.labelify(dbcol.name),
                                                        pk=dbcol.primary_key, type=coltype(dbcol),
                                                        fk_sqlcolumn=foreign_sqlcolumn)

                else:

                    column = cubetl.sql.sql.SQLColumn(name=dbcol.name,
                                                      pk=dbcol.primary_key, type=coltype(dbcol),
                                                      label=functions.labelify(dbcol.name))

                sqlcol_urn = "%s.table.%s.col.%s" % (prefix, dbtable.name, column.name)
                ctx.add(sqlcol_urn, column)
                columns.append(column)

            # Define table
            sqltable_urn = "%s.table.%s" % (prefix, dbtable.name)
            sqltable = ctx.add(sqltable_urn, cubetl.sql.sql.SQLTable(name=dbtable.name,
                                                                     connection=connection,
                                                                     columns=columns,
                                                                     label=functions.labelify(dbtable.name)))

        #printconfig = PrintConfig()
        #printflow = Chain(fork=True, steps=[printconfig])
        #result = ctx.process(printflow)

        return ctx


def coltype(dbcol):
    # TODO: Should call the DimensionClassifier facility, asking dimensions to identify the data according
    # to columns (we should have a sample of the columns)
    # TODO: This shall be standarized in CubETL
    if str(dbcol.type) in ("FLOAT", "REAL", "DECIMAL"):
        return "Float"
    elif str(dbcol.type) in ("INTEGER", "BIGINT"):
        return "Integer"
    elif str(dbcol.type) in ("DATETIME"):
        return "DateTime"
    elif str(dbcol.type) in ("BOOLEAN", "TEXT") or str(dbcol.type).startswith("VARCHAR") or str(dbcol.type).startswith("CHAR"):
        return "String"
    elif str(dbcol.type) in ("BLOB"):
        return "Binary"
    raise ValueError("Invalid column type (%s): %s" % (dbcol, dbcol.type))
