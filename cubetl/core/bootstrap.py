
from cubetl.core.context import Context
import cubetl
import getopt
import logging
import os
import sys
import traceback
import yaml
from cubetl.core import ContextProperties
from cubetl import APP_NAME_VERSION
from cubetl.core.container import Container
from cubetl.core.cubetlconfig import load_config
import pprint

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Bootstrap:

    def configure_logging(self, ctx):

        # In absence of file config
        default_level = logging.INFO if ctx.debug == False else logging.DEBUG
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=default_level)
        #logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=default_level)
        #logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

        #logging.basicConfig(
        #    level=logging.DEBUG,
        #    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
        #    datefmt="%H:%M:%S", stream=sys.stdout)

        # With file config:
        #logging.config.fileConfig('logging.conf')

    def usage(self):
        print "cubetl [-dd] [-q] [-h] [-p property=value] [-m attribute=value] [config.yaml ...] <start-node>"
        print ""
        print "    -p   set a context property"
        print "    -m   set an attribute for the start message"
        print "    -d   debug mode (can be used twice for more debug)"
        print "    -q   quiet mode (bypass print nodes)"
        print "    -h   show this help and exit"
        print "    -v   print version and exit"
        print ""
        print "  Internal nodes: "
        print "      cubetl.config.list-nodes"
        print "      cubetl.config.list-components"
        print ""

    def _split_keyvalue(self, text):
        """Return key=value pair, or key=None if format is incorrect
        """
        if (text.find('=') < 0):
            return (None, text)
        else:
            return (text[ : text.find('=')], text[text.find('=') + 1 : ])

    def parse_args(self, ctx):

        try:
            opts, arguments = getopt.gnu_getopt(ctx.argv, "p:m:dqhv", [ "help", "version"])
        except getopt.GetoptError as err:
            print str(err)
            self.usage()
            sys.exit(2)

        for o,a  in opts:
            if o in ("-h", "--help"):
                self.usage()
                sys.exit(0)
            if o in ("-v", "--version"):
                print APP_NAME_VERSION
                sys.exit(0)
            if o == "-d":
                if (ctx.debug):
                    ctx.debug2 = True
                else:
                    ctx.debug = True
            elif o == "-q":
                ctx.quiet = True
            elif o == "-p":
                (key, value) = self._split_keyvalue(a)
                if (key == None):
                    print ("Invalid property key=value definition (%s)" % (value))
                    self.usage()
                    sys.exit(2)
                logger.debug("Setting context property from command line: %s = %s" % (key, value))
                ctx.props[key] = value
            elif o == "-m":
                (key, value) = self._split_keyvalue(a)
                if (key == None):
                    print ("Invalid attribute key=value definition (%s)" % (value))
                    self.usage()
                    sys.exit(2)
                logger.debug("Setting message attribute from command line: %s = %s" % (key, value))
                ctx.start_message[key] = value

        for argument in arguments:
            if (argument.endswith('.yaml')):
                ctx.config_files.append(argument)
            else:
                if (ctx.start_node == None):
                    ctx.start_node = argument
                else:
                    print ("Only one start node can be specified (second found: '%s')" % (argument))
                    self.usage()
                    sys.exit(2)

        if (ctx.start_node == None):
            print "One starting node must be specified, but none found."
            self.usage()
            sys.exit(2)


    def init_container(self, ctx):

        cubetl.container = Container()

        try:
            configs = [os.path.dirname(os.path.realpath(__file__)) + "/../cubetl-context.yaml"]
            configs.extend([config_file for config_file in ctx.config_files])

            for configfile in configs:
                load_config(ctx, configfile)


        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error ("Could not load config: %s" % ", ".join((traceback.format_exception_only(exc_type, exc_value))))
            if (ctx.debug):
                raise
            else:
                sys.exit(3)


    def start(self, argv):

        # Set up context
        ctx = Context()
        ctx.argv = argv

        # Parse arguments
        self.parse_args(ctx)

        # Init logging
        self.configure_logging(ctx)
        logger = logging.getLogger(__name__)
        logger.info ("Starting %s" % cubetl.APP_NAME_VERSION)
        logger.debug ("Debug logging level enabled")

        # TODO: Character encoding considerations? warnings?


        # Init container (reads config)
        self.init_container(ctx)

        # Launch process
        try:
            process = cubetl.container.get_component_by_id(ctx.start_node)
        except KeyError, e:
            logger.error ("Start process '%s' not found in configuration" % ctx.start_node)
            sys.exit(1)


        count = 0

        # Launch process and consume messages
        try:
            logger.debug ("Initializing components")
            ctx.comp.initialize(process)

            logger.info ("Processing %s" % ctx.start_node)
            msgs = ctx.comp.process(process, ctx.start_message)
            for m in msgs:
                count = count + 1

            logger.debug ("%s messages resulted from the process" % count)

            logger.debug ("Finalizing components")
            ctx.comp.finalize(process)

            ctx.comp.cleanup()

        except KeyboardInterrupt as e:
            logger.error("User interrupted")

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.fatal("Error during process: %s" % ", ".join((traceback.format_exception_only(exc_type, exc_value))))

            if hasattr(ctx, "eval_error_message"):
                pp = pprint.PrettyPrinter(indent=4, depth=2)
                print pp.pformat(ctx._eval_error_message)

            traceback.print_exception(exc_type, exc_value, exc_traceback)

