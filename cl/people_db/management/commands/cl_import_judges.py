import argparse

import numpy as np
import pandas as pd
from django.core.exceptions import ValidationError

from cl.corpus_importer.court_regexes import match_court_string
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.import_judges.judge_utils import process_date_string
from cl.people_db.import_judges.populate_fjc_judges import (
    add_positions_from_row,
    make_federal_judge,
    make_mag_bk_judge,
    update_bankruptcy_and_magistrate,
)
from cl.people_db.import_judges.populate_presidents import make_president
from cl.people_db.import_judges.populate_state_judges import make_state_judge
from cl.people_db.models import Person, Position
from cl.search.models import Court
from cl.search.tasks import add_items_to_solr


class Command(VerboseCommand):
    help = "Import judge data from various files."

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s"
                % (", ".join(self.VALID_ACTIONS.keys()))
            )

        return self.VALID_ACTIONS[s]

    def ensure_input_file(self):
        if not self.options["input_file"]:
            raise argparse.ArgumentTypeError(
                "--input_file is a required argument for this action."
            )

    def add_arguments(self, parser):
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
            "skip none.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
            "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Don't change the data.",
        )
        parser.add_argument(
            "--action",
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s"
            % (", ".join(self.VALID_ACTIONS.keys())),
        )
        parser.add_argument(
            "--input_file",
            help="The input file required for certain operations.",
        )
        parser.add_argument(
            "--jurisdictions",
            help="A list of jurisdiction abbreviations for use with the "
            "assign-authors command. If no value is provided it will "
            "default to all jurisdictions. Valid options are:\n%s"
            % ", ".join(
                ["%s (%s)" % (j[0], j[1]) for j in Court.JURISDICTIONS]
            ),
            nargs="*",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.debug = options["debug"]
        self.options = options

        # Run the requested method.
        self.options["action"](self)

    def import_fjc_judges(self, infile=None):
        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        textfields = [
            "First Name",
            "Middle Name",
            "Last Name",
            "Gender",
            "Birth City",
            "Birth State",
            "Death City",
            "Death State",
        ]
        df = pd.read_csv(infile)
        df = df.replace(r"^\s+$", np.nan, regex=True)
        for x in textfields:
            df[x] = df[x].replace(np.nan, "", regex=True)
        df["Professional Career"].replace(
            to_replace=r";\sno", value=r", no", inplace=True, regex=True
        )
        for i, row in df.iterrows():
            if i < self.options["offset"]:
                continue
            if i >= self.options["limit"] > 0:
                break
            make_federal_judge(dict(row), testing=self.debug)

    def import_state_judges(self, infile=None):
        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        textfields = ["firstname", "midname", "lastname", "gender", "howended"]
        df = pd.read_excel(infile, 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, "", regex=True)
        for i, row in df.iterrows():
            make_state_judge(dict(row), testing=self.debug)

    def import_recap_judges(self, infile=None):
        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        # TODO: Read the file; sorted correctly and parse it in.
        rows = []
        for row in rows:
            pass

    def import_presidents(self, infile=None):
        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        textfields = [
            "firstname",
            "midname",
            "lastname",
            "death city",
            "death state",
        ]
        df = pd.read_excel(infile, 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, "", regex=True)
        for i, row in df.iterrows():
            make_president(dict(row), testing=self.debug)

    def import_all(self):
        datadir = self.options["input_file"]
        logger.info("importing presidents...")
        self.import_presidents(infile=f"{datadir}/presidents.xlsx")
        logger.info("importing FJC judges...")
        self.import_fjc_judges(infile=f"{datadir}/fjc-data.xlsx")
        logger.info("importing state supreme court judges...")
        self.import_state_judges(
            infile=f"{datadir}/state-supreme-court-bios-2016-04-06.xlsx"
        )
        logger.info("importing state IAC judges...")
        self.import_state_judges(
            infile=f"{datadir}/state-iac-bios-2016-04-06.xlsx"
        )

    def assign_bankruptcy_fjc(self):
        """update FJC judges with bankruptcy positions"""
        logger.info("Assigning bankruptcy courtids...")
        update_bankruptcy_and_magistrate(testing=self.debug)

    def fix_fjc_positions(self, infile=None):
        """
        Addresses issue #624.

        We had some errant regexes in the district court assignments. This code
        reassigns the court fields for these judges where the new regexes
        differs from the old ones.

        :param infile: The import file with fjc-data.xslx
        :return: None
        """

        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        textfields = [
            "firstname",
            "midname",
            "lastname",
            "gender",
            "Place of Birth (City)",
            "Place of Birth (State)",
            "Place of Death (City)",
            "Place of Death (State)",
        ]
        df = pd.read_excel(infile, 0)
        for x in textfields:
            df[x] = df[x].replace(np.nan, "", regex=True)
        df["Employment text field"].replace(
            to_replace=r";\sno", value=r", no", inplace=True, regex=True
        )
        for i, item in df.iterrows():
            fjc_id = item["Judge Identification Number"]
            p = Person.objects.get(fjc_id=fjc_id)
            logger.info(
                "Doing person with FJC ID: %s, "
                "https://courtlistener.com%s" % (fjc_id, p.get_absolute_url())
            )

            exclusions = []
            for posnum in range(1, 7):
                if posnum > 1:
                    pos_str = f" ({posnum})"
                else:
                    pos_str = ""

                if pd.isnull(item[f"Court Name{pos_str}"]):
                    continue
                courtid = match_court_string(
                    item[f"Court Name{pos_str}"], federal_district=True
                )
                if courtid is None:
                    raise Exception
                date_termination = process_date_string(
                    item[f"Date of Termination{pos_str}"]
                )
                date_start = process_date_string(
                    item[f"Commission Date{pos_str}"]
                )
                date_recess_appointment = process_date_string(
                    item[f"Recess Appointment date{pos_str}"]
                )
                if pd.isnull(date_start) and not pd.isnull(
                    date_recess_appointment
                ):
                    date_start = date_recess_appointment
                if pd.isnull(date_start):
                    # if still no start date, skip
                    date_start = None
                positions = Position.objects.filter(
                    person=p,
                    date_start=date_start,
                    date_termination=date_termination,
                    position_type="jud",
                ).exclude(pk__in=exclusions)
                position_count = positions.count()
                if position_count < 1:
                    logger.info(
                        "Couldn't find position to match '%s' on '%s' "
                        "with exclusions: %s" % (p, date_start, exclusions)
                    )
                    add_positions_from_row(
                        item, p, self.debug, fix_nums=[posnum]
                    )
                    if not self.debug:
                        add_items_to_solr.delay([p.pk], "people_db.Person")
                    continue
                elif position_count == 1:
                    # Good case. Press on!
                    position = positions[0]
                    exclusions.append(position.pk)
                elif position_count > 1:
                    logger.info(
                        "Got too many results for '%s' on '%s'. Got %s"
                        % (p, date_start, position_count)
                    )
                    continue

                if position.court.pk == courtid:
                    logger.info(
                        f"Court IDs are both '{courtid}'. No changes made."
                    )
                else:
                    logger.info(
                        "Court IDs are different! Old: %s, New: %s"
                        % (position.court.pk, courtid)
                    )
                    court = Court.objects.get(pk=courtid)
                    position.court = court

                    if not self.debug:
                        position.save()
                        add_items_to_solr.delay([p.pk], "people_db.Person")

    def process_mag_bk_entries(self, df):

        bad_record = []

        textfields = [
            "CL_ID",
            "NAME_FIRST",
            "NAME_MIDDLE",
            "NAME_LAST",
            "NAME_SUFFIX",
            "GENDER",
            "POSITION",
            "COURT",
            "START_DATE",
            "START_DATE_GRANULARITY",
            "END_DATE",
            "END_DATE_GRANULARITY",
        ]

        for x in textfields:
            df[x] = df[x].replace(np.nan, "", regex=True)
        for i, row in df.iterrows():
            if i < self.options["offset"]:
                continue
            if i >= self.options["limit"] > 0:
                break
            try:
                make_mag_bk_judge(dict(row), testing=self.debug)
            except ValidationError as e:
                bad_record.append(e[0])

        for b in bad_record:
            print(b)

    def import_mag_bk_judges(self, infile=None):

        if infile is None:
            self.ensure_input_file()
            infile = self.options["input_file"]
        df = pd.read_csv(infile)
        has_date = df["START_DATE_GRANULARITY"].notnull()
        df = df[has_date]
        df = df.replace(r"^\s+$", np.nan, regex=True)
        self.process_mag_bk_entries(df)

    VALID_ACTIONS = {
        "import-all": import_all,
        "import-fjc-judges": import_fjc_judges,
        "import-state-judges": import_state_judges,
        "import-presidents": import_presidents,
        "import-recap-judges": import_recap_judges,
        "assign-bankruptcy-fjc": assign_bankruptcy_fjc,
        "fix-fjc-positions": fix_fjc_positions,
        "import-mag-bk-judges": import_mag_bk_judges,
    }
