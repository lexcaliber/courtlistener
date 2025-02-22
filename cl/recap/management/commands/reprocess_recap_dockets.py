import sys

from django.db import IntegrityError
from django.db.models import Q
from lxml.etree import XMLSyntaxError

from cl.lib.command_utils import VerboseCommand
from cl.search.models import Docket


class Command(VerboseCommand):
    help = "Reprocess all dockets in the RECAP Archive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-pk",
            type=int,
            default=0,
            help="Skip any primary keys lower than this value. (Useful for "
            "restarts.)",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        ds = (
            Docket.objects.filter(
                # Only do ones that have HTML files *or* that have an IA XML file.
                # The latter is defined by ones that *don't* have blank
                # filepath_local fields.
                Q(html_documents__isnull=False) | ~Q(filepath_local=""),
                source__in=Docket.RECAP_SOURCES,
            )
            .distinct()
            .only("pk", "case_name")
        )
        if options["start_pk"]:
            ds = ds.filter(pk__gte=options["start_pk"])
        count = ds.count()
        xml_error_ids = []
        for i, d in enumerate(ds.iterator()):
            sys.stdout.write(
                f"\rDoing docket: {i} of {count}, with pk: {d.pk}"
            )
            sys.stdout.flush()

            try:
                d.reprocess_recap_content(do_original_xml=True)
            except IntegrityError:
                # Happens when there's wonkiness in the source data. Move on.
                continue
            except (XMLSyntaxError, IOError):
                # Happens when the local IA XML file is empty. Not sure why
                # these happen.
                xml_error_ids.append(d.pk)
                continue

        print(f"Encountered XMLSyntaxErrors/IOErrors for: {xml_error_ids}")
