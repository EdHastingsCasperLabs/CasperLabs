package io.casperlabs.casper.util.execengine

import cats.data.NonEmptyList
import cats.Applicative
import cats.effect.Sync
import cats.implicits._
import com.google.protobuf.ByteString
import io.casperlabs.catscontrib.MonadThrowable
import io.casperlabs.casper
import io.casperlabs.casper.consensus.state.{Unit => _, _}
import io.casperlabs.casper.consensus.{Block, Bond}
import io.casperlabs.casper.util.{CasperLabsProtocolVersions, ProtoUtil}
import io.casperlabs.casper.util.execengine.ExecEngineUtil.StateHash
import io.casperlabs.casper.validation.{Validation, ValidationImpl}
import io.casperlabs.crypto.Keys.PublicKey
import io.casperlabs.ipc._
import io.casperlabs.models.SmartContractEngineError
import io.casperlabs.shared.{Log, Time}
import io.casperlabs.smartcontracts.ExecutionEngineService
import io.casperlabs.storage.block._
import io.casperlabs.storage.dag._

import scala.concurrent.duration.FiniteDuration
import scala.util.Either

object ExecutionEngineServiceStub {
  type Bonds = Map[PublicKey, Long]

  import ExecEngineUtil.{MergeResult, TransformMap}

  implicit def functorRaiseInvalidBlock[F[_]: Sync] =
    casper.validation.raiseValidateErrorThroughApplicativeError[F]

  def merge[F[_]: MonadThrowable: BlockStorage](
      candidateParentBlocks: List[Block],
      dag: DagRepresentation[F]
  ): F[MergeResult[TransformMap, Block]] =
    NonEmptyList.fromList(candidateParentBlocks) map { blocks =>
      ExecEngineUtil.merge[F](blocks, dag).map(x => x: MergeResult[TransformMap, Block])
    } getOrElse {
      MergeResult.empty[TransformMap, Block].pure[F]
    }

  def validateBlockCheckpoint[F[_]: Sync: Log: BlockStorage: ExecutionEngineService: CasperLabsProtocolVersions](
      b: Block,
      dag: DagRepresentation[F]
  ): F[Either[Throwable, StateHash]] = {
    implicit val time = new Time[F] {
      override def currentMillis: F[Long]                   = 0L.pure[F]
      override def nanoTime: F[Long]                        = 0L.pure[F]
      override def sleep(duration: FiniteDuration): F[Unit] = Sync[F].unit
    }
    implicit val validation = new ValidationImpl[F]
    (for {
      parents      <- ProtoUtil.unsafeGetParents[F](b)
      merged       <- ExecutionEngineServiceStub.merge[F](parents, dag)
      preStateHash <- ExecEngineUtil.computePrestate[F](merged)
      effects      <- ExecEngineUtil.effectsForBlock[F](b, preStateHash)
      _            <- Validation[F].transactions(b, preStateHash, effects)
    } yield ProtoUtil.postStateHash(b)).attempt
  }

  def mock[F[_]](
      runGenesisWithChainSpecFunc: (
          ChainSpec.GenesisConfig
      ) => F[Either[Throwable, GenesisResult]],
      execFunc: (
          ByteString,
          Long,
          Seq[DeployItem],
          ProtocolVersion
      ) => F[Either[Throwable, Seq[DeployResult]]],
      commitFunc: (
          ByteString,
          Seq[TransformEntry]
      ) => F[Either[Throwable, ExecutionEngineService.CommitResult]],
      queryFunc: (ByteString, Key, Seq[String]) => F[Either[Throwable, Value]],
      verifyWasmFunc: ValidateRequest => F[Either[String, Unit]]
  ): ExecutionEngineService[F] = new ExecutionEngineService[F] {
    override def emptyStateHash: ByteString = ByteString.EMPTY
    override def runGenesis(
        genesisConfig: ChainSpec.GenesisConfig
    ): F[Either[Throwable, GenesisResult]] =
      runGenesisWithChainSpecFunc(genesisConfig)
    override def exec(
        prestate: ByteString,
        blocktime: Long,
        deploys: Seq[DeployItem],
        protocolVersion: ProtocolVersion
    ): F[Either[Throwable, Seq[DeployResult]]] =
      execFunc(prestate, blocktime, deploys, protocolVersion)
    override def commit(
        prestate: ByteString,
        effects: Seq[TransformEntry]
    ): F[Either[Throwable, ExecutionEngineService.CommitResult]] = commitFunc(prestate, effects)

    override def query(
        state: ByteString,
        baseKey: Key,
        path: Seq[String]
    ): F[Either[Throwable, Value]] = queryFunc(state, baseKey, path)
    override def verifyWasm(contracts: ValidateRequest): F[Either[String, Unit]] =
      verifyWasmFunc(contracts)
  }

  def noOpApi[F[_]: Applicative](): ExecutionEngineService[F] =
    mock[F](
      (_) => GenesisResult().asRight[Throwable].pure[F],
      (_, _, _, _) => Seq.empty[DeployResult].asRight[Throwable].pure[F],
      (_, _) =>
        ExecutionEngineService
          .CommitResult(ByteString.EMPTY, Seq.empty[Bond])
          .asRight[Throwable]
          .pure[F],
      (_, _, _) =>
        Applicative[F]
          .pure[Either[Throwable, Value]](Left(new SmartContractEngineError("unimplemented"))),
      _ => ().asRight[String].pure[F]
    )

}
