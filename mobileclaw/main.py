import os
import sys
import logging
import structlog
from mobileclaw.agent import AutoAgent
from mobileclaw.config import AgentConfig, CustomArgParser


def configure_logging(log_level):
    """Configure logging based on the specified log level."""
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def main():
    parser = CustomArgParser((AgentConfig,))
    if len(sys.argv) == 2 and sys.argv[1].endswith('.json'):
        config = parser.parse_json_file(json_file=os.path.abspath(sys.argv[1]))
    elif len(sys.argv) == 2 and sys.argv[1].endswith('.yaml'):
        config = parser.parse_yaml_file(yaml_file=os.path.abspath(sys.argv[1]))
    else:
        config = parser.parse_args_into_dataclasses()
    config = config[0]
    configure_logging(config.log_level)

    agent = AutoAgent(config)
    agent.serve()
    agent.stop()


if __name__ == '__main__':
    main()

